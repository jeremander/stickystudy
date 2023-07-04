from collections import Counter, defaultdict
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd
import streamlit as st


JSONDict = Dict[str, Any]

st.set_page_config(page_title = 'Kanji Flashcards', page_icon = '🇯🇵', layout = 'centered')

KANJIDIC_PATH = Path(__file__).parent / 'data/kanjidic/kanjidic.json'


@st.experimental_memo
def load_kanjidic():
    with open(KANJIDIC_PATH) as f:
        d = json.load(f)
    for (i, entry) in enumerate(d['entries']):
        entry['_id'] = i
    return d

@st.experimental_memo
def get_entries(mode: str, filters: JSONDict) -> List[JSONDict]:
    kanjidic = load_kanjidic()
    entries = kanjidic['entries']
    # get required fields
    required_fields = []
    for required_group in kanjidic['modes'][mode].get('required', []):
        required_fields += list(kanjidic['groups'][required_group]['info'])
    # apply filters to entries
    valid_entries = []
    for entry in entries:
        # skip the entry if it has an empty value in a required field
        for field in required_fields:
            if (entry.get(field) in [None, '']):
                break
        else:
            # skip the entry if it does not pass the filters
            for (filter_name, d) in kanjidic['filters'].items():
                if (filter_name in filters):
                    filter_field = d['field']
                    if (filter_field in entry):
                        val = entry[filter_field]
                        filter_vals = filters[filter_name]
                        if (val in filter_vals):
                            if (not filter_vals[val]):
                                break
                        else:
                            if (not filter_vals.get(None, False)):
                                break
            else:  # entry is valid
                valid_entries.append(entry)
    return valid_entries

@st.experimental_memo(show_spinner = False)
def get_ambiguous_values(entries: Sequence[JSONDict], groups: Sequence[str]) -> Set[Tuple[str, ...]]:
    kanjidic = load_kanjidic()
    fields = []
    for group in groups:
        info = kanjidic['groups'][group]['info']
        for field in info:
            fields.append(field)
    ctr = Counter(tuple(entry.get(field) for field in fields) for entry in entries)
    return {tup for (tup, ct) in ctr.items() if (ct > 1)}

def make_sidebar() -> None:
    kanjidic = load_kanjidic()
    modes = kanjidic['modes']
    filters = kanjidic.get('filters', {})
    with st.sidebar:
        st.caption('Choose flashcard front & back')
        chosen_mode = st.selectbox('Mode', list(modes), index = 0)
        chosen_filters = defaultdict(dict)
        for (filter_name, d) in filters.items():
            st.caption(filter_name)
            for val_entry in d['values']:
                val = val_entry['value']
                if (val is None):
                    label = 'Other'
                else:
                    label = str(val)
                is_checked = val_entry.get('default', True)
                chosen_filters[filter_name][val] = st.checkbox(label, is_checked)
    st.session_state['options'] = {'mode' : chosen_mode, 'filters' : chosen_filters}

def get_valid_entries() -> List[JSONDict]:
    options = st.session_state['options']
    mode = options['mode']
    filters = options['filters']
    return get_entries(mode, filters)

def get_random_index() -> Optional[int]:
    entries = get_valid_entries()
    num_entries = len(entries)
    if (num_entries == 0):
        return None
    random_entry = random.choice(entries)
    return random_entry['_id']

def randomize_card() -> None:
    st.session_state['entry_index'] = get_random_index()

def make_card_face(groups: Sequence[str], entry: JSONDict, front: bool, disambiguate: Optional[Sequence[str]] = None) -> None:
    kanjidic = load_kanjidic()
    if disambiguate:
        entries = get_valid_entries()
        ambiguous_vals = get_ambiguous_values(entries, groups)
    else:
        disambiguate = []
        ambiguous_vals = set()
    has_extra = any(kanjidic['groups'][group].get('extra', False) for group in groups)
    if has_extra:
        (col1, col2) = st.columns((3, 2))
    else:
        (col1, col2) = (st, None)
    all_vals = []
    def _make_group(group, primary):
        group_data = kanjidic['groups'][group]
        info = group_data['info']
        is_table = group_data.get('table', False)  # whether to display as a table
        is_extra = group_data.get('extra', False)  # whether to treat as "extra" info
        col = col2 if is_extra else col1
        d = {}
        for (field, field_name) in info.items():
            val = entry[field]
            all_vals.append(val)
            if not val:
                val = '—'
            d[field_name] = val
        if d:
            if is_table:
                df = pd.Series(d).to_frame()
                styler = df.style
                styler.hide(axis = 'columns')
                styler.set_table_styles([
                    {'selector' : 'tr', 'props' : 'line-height: 14px;'}
                ])
                col.write(styler.to_html() + '<br>', unsafe_allow_html = True)
            else:  # display as list
                for (field_name, val) in d.items():
                    if primary:  # make the value prominent
                        col.caption(field_name)
                        col.header(val)
                    else:
                        col.markdown(f'__{field_name}__: &nbsp; {val}', unsafe_allow_html = True)
    for group in groups:
        _make_group(group, primary = front)
    if (tuple(all_vals) in ambiguous_vals):  # add additional groups to disambiguate
        for group in disambiguate:
            _make_group(group, primary = False)

def present_card() -> None:
    kanjidic = load_kanjidic()
    entry_index = st.session_state['entry_index']
    if (entry_index is not None):
        entry = kanjidic['entries'][entry_index]
        mode = st.session_state['options']['mode']
        groups = kanjidic['modes'][mode]
        with st.expander('Front', expanded = True):
            disambiguate = groups.get('disambiguate')
            make_card_face(groups['front'], entry, True, disambiguate = disambiguate)
        with st.expander('Back', expanded = False):
            make_card_face(groups['back'], entry, False)

def main():
    st.title('Kanji Flashcards')
    make_sidebar()
    valid_entries = get_valid_entries()
    num_valid_entries = len(valid_entries)
    st.caption(f'({num_valid_entries:,d} cards)')
    if ('entry_index' not in st.session_state):
        randomize_card()
    st.button('Next card', on_click = randomize_card)
    present_card()

main()