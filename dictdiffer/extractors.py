
# This file is part of Dictdiffer.
#
# Copyright (C) 2013, 2014, 2015 CERN.
#
# Dictdiffer is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more
# details.

from itertools import izip_longest

from . import diff
from .utils import PathLimit


class Extractor(object):
    """Wrapper class for executing the difference extraction process.""".

    def __init__(self, extractor_update=None, ignore=None,
                 try_default=True, expand=False, path_limit=None):
        """
        :param extractor_update: Dictionary object containing an update for the
                                 utilized Extractors
        :param ignore: *ignore* parameter used by dictdiffer.diff
        :param try_default: *try_default* parameter used by dictdiffer.diff
        :param expand: *expand* parameter used by dictdiffer.diff
        :param path_limit: *path_limit* parameter used by dictdiffer.diff
        """

        self.extractors = {dict: DictExtractor,
                           list: ListExtractor,
                           set: SetExtractor,
                           'default': [DictExtractor,
                                       ListExtractor,
                                       SetExtractor]}

        if extractor_update:
            self.extractors.update(extractor_update)

        self.ignore = ignore
        self.try_default = try_default
        self.expand = expand
        self.path_limit = path_limit if path_limit else PathLimit()

    def extract(self, first, second):
        """Returns a list of differences between the first and second data
        structure."""

        return list(diff(first, second,
                         extractors=self.extractors,
                         ignore=self.ignore,
                         try_default=self.try_default,
                         expand=self.expand,
                         path_limit=self.path_limit))


class DictExtractor(object):
    """Class managing the extraction process for general dictionary objects."""

    @classmethod
    def is_applicable(cls, first, second):
        """Checks if the two presented data structure are applicable for the
        difference extraction process performed by the DictExtractor class."""

        return isinstance(first, dict) and isinstance(second, dict)

    @classmethod
    def extract(cls, first, second, node, dotted_node, ignore):
        """Returns *meta patches*, which are utilized by the dictdiffer.diff
        function.
        """

        # dictionaries are not hashable, we can't use sets
        def check(key):
            """Test if key in current node should be ignored."""
            return ignore is None \
                or (dotted_node + [key] if isinstance(dotted_node, list)
                    else '.'.join(node + [str(key)])) not in ignore

        for k in set(first.keys()+second.keys()):
            if k in first and k in second and check(k):
                yield ('change', k, k, first[k], second[k])
            elif k in first and check(k):
                yield ('delete', k, k, first[k], None)
            elif k in second and check(k):
                yield ('insert', k, k, None, second[k])


class ListExtractor(object):
    """Class managing the extraction process for list objects without semantic
    ordering."""

    @classmethod
    def is_applicable(cls, first, second):
        """Checks if the two presented data structure are applicable for the
        difference extraction process performed by the ListExtractor class."""

        return isinstance(first, list) and isinstance(second, list)

    @classmethod
    def extract(cls, first, second, node, dotted_node, ignore):
        """Returns *meta patches*, which are utilized by the dictdiffer.diff
        function.
        """

        len_first = len(first)
        len_second = len(second)

        max_length = max(len_first, len_second)

        for i in range(max_length):
            if i < min(len_first, len_second):
                yield ('change', i, i, first[i], second[i])
            elif i >= len_first:
                yield ('insert', i, i, None, second[i])
            else:
                for j in reversed(range(i, max_length)):
                    yield ('delete', j, j, first[j], None)
                return


class SetExtractor(object):
    """Class managing the extraction process for set objects."""

    @classmethod
    def is_applicable(cls, first, second):
        """Checks if the two presented data structure are applicable for the
        difference extraction process performed by the ListExtractor class."""

        return isinstance(first, set) and isinstance(second, set)

    @classmethod
    def extract(cls, first, second, node, dotted_node, ignore):
        """Returns *meta patches*, which are utilized by the dictdiffer.diff
        function.
        """

        addition = second - first
        if addition:
            yield ('insert', None, None, None, addition)
        deletion = first - second
        if deletion:
            yield ('delete', None, None, deletion, None)


class SequenceExtractor(object):
    """Class managing the extraction process for list objects, which comprise
    semantic meaning in the order of their elements."""

    class SetTuple(tuple):
        def __hash__(self):
            return hash(self + ('',))

        def __eq__(self, y):
            return (type(self) == type(y) and
                    all(map(lambda x: x[0] == x[1], izip_longest(self, y))))

    @classmethod
    def is_applicable(cls, first, second):
        """Checks if the two presented data structure are applicable for the
        difference extraction process performed by the SequenceExtractor
        class."""

        return isinstance(first, list) and isinstance(second, list)

    @classmethod
    def _make_hashable(cls, t):
        """Utility method to transform the presented data structures into
        something that is hashable, so the used diff.SequenceMatcher class can
        perform its magic."""

        if isinstance(t, list):
            return tuple(map(cls._make_hashable, t))
        elif isinstance(t, set):
            # TODO: Maybe it makes sense to just hash it here
            return cls.SetTuple(map(cls._make_hashable, sorted(t)))
        elif isinstance(t, dict):
            return hash(repr(sorted(t.items())))
        else:
            return t

    @classmethod
    def extract(cls, first, second, node, dotted_node, ignore):
        """Returns *meta patches*, which are utilized by the dictdiffer.diff
        function.
        """

        # from itertools import izip_longes
        from difflib import SequenceMatcher
        sequence = SequenceMatcher(None,
                                   cls._make_hashable(first),
                                   cls._make_hashable(second))

        latest_insertions = 0
        latest_deletions = 0

        for _tuple in sequence.get_opcodes():
            if _tuple[0] == 'insert':
                for i, new_path in enumerate(range(_tuple[3], _tuple[4])):
                    yield ('insert',
                           _tuple[1]+i+latest_insertions-latest_deletions,
                           new_path,
                           None, second[new_path])
                latest_insertions += _tuple[4]-_tuple[3]
            elif _tuple[0] == 'delete':
                for index in reversed(range(_tuple[1], _tuple[2])):
                    yield ('delete',
                           index-latest_deletions+latest_insertions,
                           index-latest_deletions+latest_insertions,
                           first[index], None)
                latest_deletions += _tuple[2]-_tuple[1]
            elif _tuple[0] == 'replace':
                old_range = range(_tuple[1], _tuple[2])
                new_range = range(_tuple[3], _tuple[4])

                changes_index = min(len(old_range), len(new_range))

                for old_path, new_path in zip(old_range, new_range):
                    yield ('change',
                           old_path+latest_insertions-latest_deletions,
                           new_path,
                           first[old_path], second[new_path])
                    last_old_path = old_path+latest_insertions-latest_deletions

                if len(old_range) < len(new_range):
                    for new_path in new_range[changes_index:]:
                        yield ('insert', last_old_path+1, new_path, None,
                               second[new_path])
                        last_old_path += 1
                        latest_insertions += 1
                elif len(old_range) > len(new_range):
                    for old_path in reversed(old_range[changes_index:]):
                        yield ('delete',
                               old_path+latest_insertions-latest_deletions,
                               old_path+latest_insertions-latest_deletions,
                               first[old_path], None)
                    latest_deletions += len(old_range)-changes_index


def get_default_extractors():
    """Returns a dictionary object containing a default configuration for the 
    extraction process, utilizing the DictExtractor, ListExtractor and
    SetExtractor classes."""

    return {dict: DictExtractor,
            list: ListExtractor,
            set: SetExtractor,
            'default': [DictExtractor, ListExtractor, SetExtractor]}