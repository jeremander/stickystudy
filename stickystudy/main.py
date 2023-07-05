#!/usr/bin/env python3
"""Utilities for managing StickyStudy decks."""

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from datetime import datetime
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from tabulate import tabulate

from stickystudy import DATA_DIR, LOGGER
from stickystudy.utils import KUN_COL, MEANING_COL, ON_COL, KanjiData, StickyStudyDeck, get_deck_path, get_default_deck_path


KANJI_MASTER = DATA_DIR / 'kanji_list.tsv'
KANJI_CURRENT = DATA_DIR / 'kanji_list_current.tsv'
DECK_SUBSETS = DATA_DIR / 'deck_subsets.json'

ASCENDING_BY_SORT_KEY = {
    'jlpt': False,
    'grade': True,
    'freq': True
}

# SUBCOMMANDS

class Subcommand:
    """Class providing functionality for a subcommand."""

    def configure_parser(self, parser: ArgumentParser) -> None:
        """Configures the subparser for the subcommand."""

    def main(self, args: Namespace) -> None:
        """Executes the main logic of the subcommand."""


class Add(Subcommand):
    """Add kanji from a master list to the current study list"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('-i', '--input-file', default = KANJI_MASTER, help = 'input TSV file of kanji data')
        parser.add_argument('-o', '--output-file', default = KANJI_CURRENT, help = 'output TSV file of current kanji data')
        parser.add_argument('-n', '--num-kanji', type = int, default = 3, help = 'number of kanji to add')
        parser.add_argument('-s', '--sort-by', nargs = '+', default = ['jlpt', 'grade', 'freq'], help = 'sort criteria')

    def main(self, args: Namespace) -> None:
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


class Fix(Subcommand):
    """Fix mojibake in StickyStudy CSV export"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('input_file', help = 'CSV file exported by StickyStudy')

    def main(self, args: Namespace) -> None:
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


class SyncKanji(Subcommand):
    """Sync kanji TSV with StickyStudy decks"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('-i', '--input-file', default = KANJI_CURRENT, help = 'input TSV file of kanji data')
        parser.add_argument('-o', '--output-prefix', default = 'Study-Kanji', help = 'output prefix (either full path prefix, or relative to StickyStudy deck directory)')
        parser.add_argument('--levels', nargs = '+', required = True, type = int, choices = range(5, 0, -1), help = 'JLPT levels to include')

    def main(self, args: Namespace) -> None:
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
                assert (set(orig_deck.data.question).issubset(set(new_deck.data.question)))
                merged_df = pd.merge(new_deck.data, orig_deck.data[['question', 'study_data']], how = 'outer', left_on = 'question', right_on = 'question', validate = 'one_to_one')
                new_df = StickyStudyDeck(header = orig_deck.header, data = merged_df)
            LOGGER.info(msg)
            new_df.save(path)


class SyncSubsets(Subcommand):
    """Sync overlapping StickyStudy decks"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('-i', '--input-file', default = DECK_SUBSETS, help = 'input JSON file mapping from deck names to lists of subset decks')

    def sync_subsets(self, deck: str, subsets: list[str]) -> None:
        LOGGER.info(f'\t{deck}: ' + ', '.join(subsets))
        d: Optional[StickyStudyDeck] = None
        for subdeck in subsets:
            path = get_deck_path(subdeck)
            d1 = StickyStudyDeck.load(path)
            d = d1 if (d is None) else (d | d1)
        output_path = get_deck_path(deck)
        LOGGER.info(f'\tSaving {output_path}')
        assert isinstance(d, StickyStudyDeck)
        d.save(output_path)

    def main(self, args: Namespace) -> None:
        import networkx as nx
        LOGGER.info(f'Loading deck subsets from {args.input_file}')
        with open(args.input_file) as f:
            subsets = json.load(f)
        dg = nx.DiGraph()
        for (deck, subdecks) in subsets.items():
            for subdeck in subdecks:
                dg.add_edge(subdeck, deck)
        assert nx.is_directed_acyclic_graph(dg)
        # process decks in topological order
        for deck in nx.topological_sort(dg):
            if (deck in subsets) and bool(subsets[deck]):
                self.sync_subsets(deck, subsets[deck])


if __name__ == '__main__':

    parser = ArgumentParser(description = __doc__)
    subparsers = parser.add_subparsers(help = 'subcommand', dest = 'subcommand')

    subcommands_by_name = {
        'add': Add(),
        'fix': Fix(),
        'sync-kanji': SyncKanji(),
        'sync-subsets': SyncSubsets(),
    }
    for (subcmd, obj) in subcommands_by_name.items():
        doc = obj.__class__.__doc__
        subparser = subparsers.add_parser(subcmd, help = doc, description = doc, formatter_class = ArgumentDefaultsHelpFormatter)
        obj.configure_parser(subparser)

    args = parser.parse_args()
    obj = subcommands_by_name[args.subcommand]
    obj.main(args)
