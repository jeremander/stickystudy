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
from stickystudy.deck import DECK_COLS, StickyStudyDeck, get_deck_path, get_default_deck_path
from stickystudy.utils import KUN_COL, MEANING_COL, ON_COL, KanjiData


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
        import ftfy
        with open(args.infile) as f:
            s = f.read()
        fixed = ftfy.fix_text(s)
        lines = fixed.splitlines()
        fixed = '\n'.join(lines[2:]) + '\n'
        header = "kanji\ton'yomi\tkun'yomi\tmeaning\tpractice_data"
        print(header)
        print(fixed)


class ListDecks(Subcommand):
    """List all installed StickyStudy decks"""

    def main(self, args: Namespace) -> None:
        deck_path = get_default_deck_path()
        LOGGER.info(f'Decks are in {deck_path}\n')
        for p in sorted(deck_path.glob('*.txt')):
            print(p.stem.replace('-', ' '))


class SyncCopy(Subcommand):
    """Sync a StickyStudy deck with a copy of itself, adding any new flashcards from the source deck to the target copy"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('input_decks', nargs = '+', help = 'deck names to sync with copies')
        parser.add_argument('-l', '--label', default = 'R', help = 'label to append to the copied decks')
        parser.add_argument('--with-kanji', nargs = '?', default = None, const = KANJI_CURRENT, help = 'only include words where all kanji are in the given kanji TSV file (and at least one kanji is present)')

    def main(self, args: Namespace) -> None:
        if args.with_kanji:
            kanji_df = KanjiData.load(args.with_kanji)
        for src_name in args.input_decks:
            src_path = get_deck_path(src_name)
            LOGGER.info(f'Loading {src_path}')
            src_deck = StickyStudyDeck.load(src_path)
            target_name = f'{src_name} ({args.label})'
            target_path = get_deck_path(target_name)
            if target_path.exists():
                LOGGER.info(f'\tUpdating {target_path}')
                target_deck = StickyStudyDeck.load(target_path)
                target_deck = src_deck.update_other(target_deck)
            else:
                LOGGER.info(f'\tCreating a copy at {target_path}')
                target_deck = src_deck.update_other(None)
            if args.with_kanji:
                num_entries = len(target_deck)
                target_deck = target_deck.filter_kanji(kanji_df.kanji, must_include_kanji = True)
                if (len(target_deck) < num_entries):
                    LOGGER.info(f'\tFiltered from {num_entries:,d} to {len(target_deck):,d} words')
            target_deck.save(target_path)


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
                new_deck = StickyStudyDeck(header = orig_deck.header, data = merged_df)
            LOGGER.info(msg)
            new_deck.save(path)


class SyncSubsets(Subcommand):
    """Sync overlapping StickyStudy decks"""

    def configure_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument('-i', '--input-file', default = DECK_SUBSETS, help = 'input JSON file mapping from deck names to lists of subset decks')

    def sync_children_to_parents(self, parent: str, children: list[str]) -> None:
        d: Optional[StickyStudyDeck] = None
        # get the union of subdecks
        for child in children:
            path = get_deck_path(child)
            d1 = StickyStudyDeck.load(path)
            d = d1 if (d is None) else (d | d1)
        output_path = get_deck_path(parent)
        if output_path.exists():
            # retain each flashcard from the original deck, if it's in a subdeck and it was studied more recently
            deck = StickyStudyDeck.load(output_path)
            df1 = d.data.set_index(DECK_COLS[:-1])  # type: ignore
            df2 = deck.data.set_index(DECK_COLS[:-1])
            df2 = df2.loc[df2.index.intersection(df1.index)]
            d1 = StickyStudyDeck(d.header, df1.reset_index())  # type: ignore
            d2 = StickyStudyDeck(deck.header, df2.reset_index())
            d = d1 | d2
        LOGGER.info(f'\t\tSaving {output_path}')
        assert isinstance(d, StickyStudyDeck)
        d.save(output_path)

    def sync_parent_to_child(self, parent: str, child: str) -> None:
        parent_deck = StickyStudyDeck.load(get_deck_path(parent))
        child_path = get_deck_path(child)
        child_deck = StickyStudyDeck.load(child_path)
        df2 = child_deck.data.set_index(DECK_COLS[:-1])
        df1 = parent_deck.data.set_index(DECK_COLS[:-1]).loc[df2.index]
        d1 = StickyStudyDeck(parent_deck.header, df1.reset_index())
        d2 = StickyStudyDeck(child_deck.header, df2.reset_index())
        d = d1 | d2
        LOGGER.info(f'\t\tSaving {child_path}')
        d.save(child_path)

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
        LOGGER.info('Syncing children to parents')
        for parent in nx.topological_sort(dg):
            if (parent in subsets) and bool(subsets[parent]):
                children = subsets[parent]
                LOGGER.info(f'\t{parent} <- ' + ', '.join(children))
                self.sync_children_to_parents(parent, children)
        LOGGER.info('Syncing parents to children')
        dg = dg.reverse()
        for parent in nx.topological_sort(dg):
            children = list(dg.succ[parent])
            if children:
                LOGGER.info(f'\t{parent} -> ' + ', '.join(children))
                for child in children:
                    self.sync_parent_to_child(parent, child)


def main() -> None:
    """Main entry point for stickystudy program."""
    parser = ArgumentParser(description = __doc__)
    subparsers = parser.add_subparsers(help = 'subcommand', dest = 'subcommand')
    subcommands_by_name = {
        'add': Add(),
        'fix': Fix(),
        'list-decks': ListDecks(),
        'sync-copy': SyncCopy(),
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


if __name__ == '__main__':

    main()
