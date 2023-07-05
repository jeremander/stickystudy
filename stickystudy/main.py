#!/usr/bin/env python3
"""Utilities for managing StickyStudy decks."""

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
from tabulate import tabulate

from stickystudy import DATA_DIR, LOGGER
from stickystudy.utils import KUN_COL, MEANING_COL, ON_COL, KanjiData, StickyStudyDeck, get_default_deck_path


KANJI_MASTER = DATA_DIR / 'kanji_list.tsv'
KANJI_CURRENT = DATA_DIR / 'kanji_list_current.tsv'

ASCENDING_BY_SORT_KEY = {
    'jlpt': False,
    'grade': True,
    'freq': True
}

# SUBCOMMANDS

def do_add(args: Namespace) -> None:
    """Add kanji from a master list to the current study list"""
    try:
        src_df = KanjiData.load(args.input_file)
        dest_df = KanjiData.load(args.output_file)
    except OSError as e:
        raise SystemExit(e)
    # remove kanji we have already studied
    src_df = src_df[~src_df.kanji.isin(dest_df.kanji)]
    LOGGER.info(f'{len(src_df)} unlearned kanji remaining in source list.')
    ascending = [ASCENDING_BY_SORT_KEY[key] for key in args.sort_by]
    src_df = src_df.sort_values(by = args.sort_by, ascending = ascending).head(args.num_kanji)
    src_df['time_learned'] = datetime.now().isoformat()
    LOGGER.info(f'Learning {len(src_df)} kanji:\n')
    if (len(src_df) > 0):
        fixna = lambda val : '—' if pd.isna(val) else str(val)
        study_df = src_df.set_index('kanji').applymap(fixna).transpose()
        # reorder rows
        ref_col = 'ref_sh_kk_2'  # 2nd edition of SH-KK
        rows = [ref_col, 'jlpt', 'grade', 'freq', 'strokes', 'learned', "on'yomi", "kun'yomi", 'meaning', "KD on'yomi", "KD kun'yomi", 'KD meaning']
        study_df = study_df.loc[rows]
        print(tabulate(study_df, headers = study_df.columns, showindex = 'always', tablefmt = 'rounded_grid') + '\n')
    response = input('Add these kanji to the current study list? [y/n] ')
    if response.lower().strip().startswith('y'):
        dest_df = KanjiData(pd.concat([dest_df, src_df]))
        dest_df.save(args.output_file)
    else:
        LOGGER.info('\nNo new kanji added.')

def do_fix(args: Namespace) -> None:
    """Fix mojibake in StickyStudy CSV export"""
    import ftfy
    with open(args.infile) as f:
        s = f.read()
    fixed = ftfy.fix_text(s)
    lines = fixed.splitlines()
    fixed = '\n'.join(lines[2:]) + '\n'
    header = "kanji\ton'yomi\tkun'yomi\tmeaning\tpractice_data"
    print(header)
    print(fixed)

def do_sync(args: Namespace) -> None:
    """Sync kanji TSV with StickyStudy decks"""
    # StickyStudy columns: question, on, kun, answer, metadata
    cols = ['kanji', "on'yomi", "kun'yomi", 'meaning']
    levels = set(args.levels)
    level_str = ','.join(map(str, sorted(levels)))
    df = KanjiData.load(args.input_file)
    df = KanjiData(df[df.jlpt.isin(levels)][cols])
    LOGGER.info(f'{len(df):,d} entries in JLPT levels {sorted(levels)}.')
    prefix = args.output_prefix
    if ('/' not in args.output_prefix):  # relative path
        prefix = str(get_default_deck_path() / prefix)
    prefix += f'-N{level_str}'
    for (name, col) in [('ON', ON_COL), ('KUN', KUN_COL), ('MEANING', MEANING_COL)]:
        new_deck = StickyStudyDeck(header = None, data = df.get_answer_df(col))
        path = Path(f'{prefix}-{name}.txt')
        msg = f'Saving {path}'
        if path.exists():
            orig_deck = StickyStudyDeck.load(path)
            msg += ' (preserving current study data)'
            assert (set(orig_deck.data.kanji).issubset(set(new_deck.data.kanji)))
            merged_df = pd.merge(new_deck.data, orig_deck.data[['kanji', 'study_data']], how = 'outer', left_on = 'kanji', right_on = 'kanji', validate = 'one_to_one')
            new_df = StickyStudyDeck(header = orig_deck.header, data = merged_df)
        LOGGER.info(msg)
        new_df.save(path)


if __name__ == '__main__':

    parser = ArgumentParser(description = __doc__)
    subparsers = parser.add_subparsers(help = 'subcommand', dest = 'subcommand')

    def _get_subcmd(subcommand: str) -> Callable[[Namespace], None]:
        return globals()[f'do_{subcommand}']

    def _add_parser(subcommand: str) -> ArgumentParser:
        func = _get_subcmd(subcommand)
        return subparsers.add_parser(subcommand, help = func.__doc__, description = func.__doc__, formatter_class = ArgumentDefaultsHelpFormatter)

    p_update = _add_parser('add')
    p_update.add_argument('-i', '--input-file', default = KANJI_MASTER, help = 'input TSV file of kanji data')
    p_update.add_argument('-o', '--output-file', default = KANJI_CURRENT, help = 'output TSV file of current kanji data')
    p_update.add_argument('-n', '--num-kanji', type = int, default = 3, help = 'number of kanji to add')
    p_update.add_argument('-s', '--sort-by', nargs = '+', default = ['jlpt', 'grade', 'freq'], help = 'sort criteria')

    p_fix = _add_parser('fix')
    p_fix.add_argument('input_file', help = 'CSV file exported by StickyStudy')

    p_sync = _add_parser('sync')
    p_sync.add_argument('-i', '--input-file', default = KANJI_CURRENT, help = 'input TSV file of kanji data')
    p_sync.add_argument('-o', '--output-prefix', default = 'Study-Kanji', help = 'output prefix (either full path prefix, or relative to StickyStudy deck directory)')
    p_sync.add_argument('--levels', nargs = '+', required = True, type = int, choices = range(5, 0, -1), help = 'JLPT levels to include')

    args = parser.parse_args()

    func = _get_subcmd(args.subcommand)
    func(args)
