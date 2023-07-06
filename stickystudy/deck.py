from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Self

import pandas as pd

from stickystudy.utils import KUN_COL, ON_COL, AnyPath


DECK_COLS = ['question', ON_COL, KUN_COL, 'answer', 'study_data']


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


@dataclass(repr = False)
class StickyStudyDeck:
    """A DataFrame representing a StickyStudy deck."""

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
        df = pd.read_table(infile, skiprows = skiprows, names = DECK_COLS)
        # extract timestamps
        df['timestamp'] = pd.Series([int(sd[1:-1].split('_')[0]) if sd else pd.NA for sd in df.study_data], dtype = 'Int64')
        return cls(header, df)

    def save(self, outfile: AnyPath) -> None:
        """Saves data to a StickyStudy deck file, including any header lines."""
        if self.header:  # write the header
            with open(outfile, 'w') as f:
                for line in self.header:
                    print(line, file = f, end = '')
        cols = DECK_COLS if ('study_data' in self.data.columns) else DECK_COLS[:-1]
        self.data[cols].to_csv(outfile, index = False, header = False, sep = '\t', mode = 'a')

    def __or__(self, other: object) -> Self:
        """Takes the union of two decks.
        If duplicate entries occur, takes the entry with the newer timestamp."""
        if isinstance(other, StickyStudyDeck):
            df = pd.concat([self.data, other.data]).sort_values(by = 'timestamp').drop_duplicates(DECK_COLS[:-1], keep = 'last')
            return self.__class__(self.header, df)
        return NotImplemented

    def update_other(self, other: Optional[Self]) -> Self:
        """Adds any cards in the current deck to a target deck which are not already in the target deck.
        New cards will have empty study data; existing cards will retain their current status.
        If other = None, treats the target deck as empty."""
        df = deepcopy(self.data)
        df['study_data'] = ''
        if (other is None):
            return self.__class__(None, df)
        df = pd.concat([other.data, df]).drop_duplicates(DECK_COLS[:-1], keep = 'first')
        return self.__class__(other.header, df)
