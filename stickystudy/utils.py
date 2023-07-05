from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
from typing import ClassVar, Optional, Self

import pandas as pd

from stickystudy import LOGGER


AnyPath = Path | str

KANJI_COL = 'kanji'
ON_COL = "on'yomi"
KUN_COL = "kun'yomi"
MEANING_COL = 'meaning'


def get_default_deck_path() -> Path:
    """Gets the default path to the StickyStudy decks stored in the user's iCloud folder.
    This assumes the user is running MacOS."""
    app_dir = 'iCloud~com~justinnightingale~stickystudykanji'
    path = Path(os.environ['HOME']) / f'iCloud/{app_dir}/Documents'
    assert path.exists()
    return path

def get_deck_path(name: str) -> Path:
    """Given a deck name, gets the absolute path to that deck."""
    name = name.replace(' ', '-')
    return get_default_deck_path() / f'{name}.txt'


class KanjiData(pd.DataFrame):
    """A DataFrame storing kanji data (kanji, readings, meaning, JLPT level, etc.)."""

    @classmethod
    def load(cls, infile: AnyPath) -> Self:
        """Loads kanji data from a TSV file.
        Fields should include "kanji", "on'yomi", "kun'yomi", "meaning", and "jlpt"."""
        LOGGER.info(f'Loading kanji data from {infile}')
        int_cols = ['jlpt', 'ref_sh_kk', 'ref_sh_kk_2']
        dtypes = {col: 'Int64' for col in int_cols}
        df = cls(pd.read_table(infile, dtype = dtypes))
        LOGGER.info(f'Loaded {len(df):,d} entries')
        return df

    def save(self, outfile: AnyPath) -> None:
        """Saves kanji data to a TSV file."""
        LOGGER.info(f'Saving kanji data to {outfile}')
        self.to_csv(outfile, sep = '\t', index = False)
        LOGGER.info(f'Saved {len(self):,d} entries')

    def get_answer_df(self, col: str) -> pd.DataFrame:
        """Given a column, creates a new DataFrame whose question column becomes the relevant column.
        Disambiguation is performed appropriately."""
        fixval = lambda val : val if isinstance(val, str) else None
        on_counts = Counter(self[ON_COL])
        kun_counts = Counter(self[KUN_COL])
        on_kun_counts = Counter((fixval(on), fixval(kun)) for (on, kun) in zip(self[ON_COL], self[KUN_COL]))
        meaning_counts = Counter(self[MEANING_COL])
        on_meaning_counts = Counter((fixval(on), fixval(meaning)) for (on, meaning) in zip(self[ON_COL], self[MEANING_COL]))
        field_map = {ON_COL : 'ON', KUN_COL : 'KUN', MEANING_COL : 'MEANING'}
        questions, info = [], []
        def _field_str(field: str, elt: Optional[str]) -> str:
            return field_map[field] + ': ' + (elt or '[N/A]')
        for tup in self[[ON_COL, KUN_COL, MEANING_COL]].itertuples():
            on = fixval(tup[1])
            kun = fixval(tup[2])
            meaning = fixval(tup[3])
            if (col == ON_COL):
                val = on
            elif (col == KUN_COL):
                val = kun
            else:
                val = meaning
            has_val = False
            elts: dict[str, Optional[str]] = {}
            if (col == ON_COL):
                if on:
                    elts[ON_COL] = on
                    has_val = True
                elif kun:
                    elts[KUN_COL] = kun
                if (on_counts[on] > 1):
                    elts[KUN_COL] = kun
                if (on_kun_counts[(on, kun)] > 1):
                    elts[MEANING_COL] = meaning
                    if (not kun):
                        del elts[KUN_COL]
            elif (col == KUN_COL):
                if kun:
                    elts[KUN_COL] = kun
                    has_val = True
                elif on:
                    elts[ON_COL] = on
                if (kun_counts[kun] > 1):
                    elts[ON_COL] = on
                if (on_kun_counts[(on, kun)] > 1):
                    elts[MEANING_COL] = meaning
                    if (not on):
                        del elts[ON_COL]
            else:  # meaning
                if meaning:
                    elts[MEANING_COL] = meaning
                    has_val = True
                if (meaning_counts[meaning] > 1):
                    elts[ON_COL] = on
                if (on_meaning_counts[(on, meaning)] > 1):
                    elts[KUN_COL] = kun
            if (len(elts) == 1) and has_val:  # no need to label the field
                question = val
            else:
                segs = [_field_str(field, elts[field]) for field in field_map if (field in elts)]
                question = '; '.join(segs)
            questions.append(question)
            elts2 = {}
            for (val, field) in [(on, ON_COL), (kun, KUN_COL), (meaning, MEANING_COL)]:
                if val and (not elts.get(field)):
                    elts2[field] = val
            segs = [_field_str(field, elts2[field]) for field in field_map if (field in elts2)]
            info.append('\u0085'.join(segs))
        return pd.DataFrame({'kanji' : self[KANJI_COL], 'question' : questions, '' : ['' for _ in range(len(self))], 'info' : info})


@dataclass(repr = False)
class StickyStudyDeck:
    """A DataFrame representing a StickyStudy deck."""

    columns: ClassVar[list[str]] = ['question', ON_COL, KUN_COL, 'answer', 'study_data']

    header: Optional[list[str]]
    data: pd.DataFrame

    @classmethod
    def load(cls, infile: AnyPath) -> Self:
        """Loads kanji data from a StickyStudy deck file.
        Stores the header lines in the `_header` attribute."""
        header = []
        skiprows = 0
        with open(infile) as f:
            header.append(next(f))
            header.append(next(f))
            if header[-1].startswith('-' * 5):
                skiprows = 2
        # names = ['kanji', 'question', '', 'info', 'study_data']
        df = pd.read_table(infile, skiprows = skiprows, names = cls.columns)
        # extract timestamps
        df['timestamp'] = pd.Series([int(sd[1:-1].split('_')[0]) if sd else pd.NA for sd in df.study_data], dtype = 'Int64')
        return cls(header, df)

    def save(self, outfile: AnyPath) -> None:
        """Saves data to a StickyStudy deck file, including any header lines."""
        if self.header:  # write the header
            with open(outfile, 'w') as f:
                for line in self.header:
                    print(line, file = f, end = '')
        self.data[self.columns].to_csv(outfile, index = False, header = False, sep = '\t', mode = 'a')

    def __or__(self, other: object) -> Self:
        """Takes the union of two decks.
        If duplicate entries occur, takes the entry with the newer timestamp."""
        if isinstance(other, StickyStudyDeck):
            df = pd.concat([self.data, other.data]).sort_values(by = 'timestamp').drop_duplicates(self.columns[:-1], keep = 'last')
            return self.__class__(self.header, df)
        return NotImplemented