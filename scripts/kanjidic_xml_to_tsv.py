#!/usr/bin/env python3

import argparse
from collections import defaultdict
import csv
import sys

from jamdict.kanjidic2 import Kanjidic2XMLParser

# reference numbering systems to include
DIC_REFS = ['sh_kk', 'sh_kk2']


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description = 'Convert kanjidic XML into a TSV file')
    parser.add_argument('kanjidic', help = 'kanjidic XML file')
    args = parser.parse_args()

    p = Kanjidic2XMLParser()
    print(f'Parsing {args.kanjidic}', file = sys.stderr)
    data = p.parse_file(args.kanjidic)

    # make column names
    columns = ['kanji', 'codepoint', 'strokes', 'grade', 'freq', 'jlpt']
    for dic_ref in DIC_REFS:
        columns.append(f'ref_{dic_ref}')
    columns += ["on'yomi", "kun'yomi", 'meanings']

    writer = csv.writer(sys.stdout, delimiter = '\t')
    writer.writerow(columns)

    for c in data.characters:
        entry = [c.literal, ord(c.literal), c.stroke_count, c.grade, c.freq, c.jlpt]
        # reference numbers
        d = {ref.dr_type : ref.value for ref in c.dic_refs}
        for dic_ref in DIC_REFS:
            entry.append(d.get(dic_ref))
        # readings/meanings
        assert (len(c.rm_groups) <= 1)
        if c.rm_groups:
            # readings
            rm_group = c.rm_groups[0]
            d = defaultdict(list)
            for reading in rm_group.readings:
                if (reading.r_type in ['ja_on', 'ja_kun']):
                    d[reading.r_type].append(reading.value)
            on_yomi = ', '.join(d.get('ja_on', []))
            kun_yomi = ', '.join(d.get('ja_kun', [])).replace('.', '･')
            # meanings
            meanings = ', '.join(meaning.value for meaning in rm_group.meanings if (meaning.m_lang == ''))
            entry += [on_yomi, kun_yomi, meanings]
        else:
            entry += ['', '', '']
        writer.writerow(entry)
