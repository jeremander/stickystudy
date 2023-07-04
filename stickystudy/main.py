#!/usr/bin/env python3
"""Utilities for managing StickyStudy decks."""

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from pathlib import Path

import pandas as pd
from tabulate import tabulate

from stickystudy import LOGGER
from stickystudy.utils import KUN_COL, MEANING_COL, ON_COL, KanjiData


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
    src_df = src_df.sort_values(by = args.sort_by, ascending = ascending).head(args.num_kanji).astype({'jlpt': int})
    LOGGER.info(f'Learning {len(src_df)} kanji:\n')
    if (len(src_df) > 0):
        study_df = src_df.set_index('kanji').transpose()
        # reorder rows
        rows = ['ref_sh_kk', 'jlpt', 'grade', 'freq', 'strokes', 'learned', "on'yomi", "kun'yomi", 'meaning', "KD on'yomi", "KD kun'yomi", 'KD meaning']
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
    df = df[df.jlpt.isin(levels)][cols]
    LOGGER.info(f'{len(df):,d} entries in JLPT levels {sorted(levels)}.')
    prefix = f'{args.output_prefix}-N{level_str}'
    for (name, col) in [('ON', ON_COL), ('KUN', KUN_COL), ('MEANING', MEANING_COL)]:
        new_df = df.get_answer_df(col)
        path = Path(f'{prefix}-{name}.txt')
        msg = f'Saving {path}'
        header = []
        if path.exists():
            skiprows = 0
            with open(path) as f:
                header.append(next(f))
                header.append(next(f))
                if header[-1].startswith('-' * 5):
                    skiprows = 2
            names = list(new_df.columns) + ['study_data']
            orig_df = pd.read_csv(path, sep = '\t', skiprows = skiprows, names = names)
            msg += ' (preserving current study data)'
            assert (set(orig_df.kanji).issubset(set(new_df.kanji)))
            new_df = pd.merge(new_df, orig_df[['kanji', 'study_data']], how = 'outer', left_on = 'kanji', right_on = 'kanji', validate = 'one_to_one')
        LOGGER.info(msg)
        if header:  # write the header
            with open(path, 'w') as f:
                for line in header:
                    print(line, file = f, end = '')
        new_df.to_csv(path, index = False, header = False, sep = '\t', mode = 'a')


if __name__ == '__main__':

    fcls = ArgumentDefaultsHelpFormatter
    parser = ArgumentParser(description = __doc__)
    subparsers = parser.add_subparsers(help = 'subcommand', dest = 'subcommand')

    p_update = subparsers.add_parser('add', help = do_add.__doc__, formatter_class = fcls)
    p_update.add_argument('input_file', help = 'input TSV file of target kanji data')
    p_update.add_argument('output_file', help = 'output TSV file of current kanji data')
    p_update.add_argument('-n', '--num-kanji', type = int, default = 3, help = 'number of kanji to add')
    p_update.add_argument('-s', '--sort-by', nargs = '+', default = ['jlpt', 'grade', 'freq'], help = 'sort criteria')

    p_fix = subparsers.add_parser('fix', help = do_fix.__doc__, formatter_class = fcls)
    p_fix.add_argument('input_file', help = 'CSV file exported by StickyStudy')

    p_sync = subparsers.add_parser('sync', help = do_sync.__doc__, formatter_class = fcls)
    p_sync.add_argument('input_file', help = 'input TSV file of kanji data')
    p_sync.add_argument('-o', '--output-prefix', required = True, help = 'output prefix')
    p_sync.add_argument('--levels', nargs = '+', required = True, type = int, choices = range(5, 0, -1), help = 'JLPT levels to include')

    args = parser.parse_args()

    func = globals()[f'do_{args.subcommand}']
    func(args)
