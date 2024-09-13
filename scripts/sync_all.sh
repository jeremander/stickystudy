#!/usr/bin/env bash

echo "Syncing kanji from known list to JLPT study deck"
stickystudy sync-kanji --levels 5 4 3

echo "Syncing deck subsets"
stickystudy sync-subsets

echo "Syncing reverse study decks"
stickystudy sync-copy "All Vocab" --label W --with-kanji
