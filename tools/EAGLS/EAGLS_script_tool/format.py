#!/usr/bin/env python

import os
import re
import sys

engine_pre = re.compile(r'(.+)(["\)])([0-9]+\(.*)', re.VERBOSE)
semicolon_post1 = re.compile(r'(.+}[0-9];)(.+)', re.VERBOSE)
semicolon_post2 = re.compile(r'(}[0-9];)(.+)', re.VERBOSE)
curlybracket_pre = re.compile(r'(.+)}(.*)', re.VERBOSE)
conditional_pre = re.compile(r'(.+\))([0-9]+,[0-9]+\(.+\){)', re.VERBOSE)
conditional_post = re.compile(r'(.+\){)([0-9]+\()', re.VERBOSE)
var_pre = re.compile(r'\)(_.*)', re.VERBOSE)
remove_blanks = re.compile(r'\n\n', re.VERBOSE)
dialogue_pre = re.compile(r'(.+)(&[0-9]+".*")', re.VERBOSE)
dialogue = re.compile(r'&([0-9]+)"(.*)"', re.VERBOSE)
dialogue_unify = re.compile(r'(&[0-9]+".*")\n\n&', re.VERBOSE)
dialogue_sep1 = re.compile(r'(&[0-9]+".*")(.+)', re.VERBOSE)
dialogue_sep2 = re.compile(r'\)\n(&[0-9]+".*")', re.VERBOSE)
dialogue_sep3 = re.compile(r'(&[0-9]+".*")\n(?!&)', re.VERBOSE)
name_pre = re.compile(r'(.+)\#(.*)', re.VERBOSE)
name = re.compile(r'(.*\n)(\#.*\n&[0-9]+".*")', re.VERBOSE)
doubles = re.compile(r'\n\n\n', re.VERBOSE)
voiced = re.compile(r'(\#.*\n;.*\n&[0-9]+")"')

def walk_file(file: str):
    if not os.path.isfile(file):
        raise RuntimeError(f"{file} not found")
    with open(file, newline="", encoding="utf8") as fpin, \
            open(file + ".new", "w", newline="", encoding="utf8") as fpout:
        lines = fpin.read()
        # unify line endings
        lines = lines.replace("\r\n", "\n")
        lines = lines.replace("\r", "\n")
        # move engine statements to its own line
        while engine_pre.search(lines):
            lines = engine_pre.sub(r'\1\2\n\3', lines)
        while semicolon_post1.search(lines):
            lines = semicolon_post1.sub(r'\n\1\n\2', lines)
        while curlybracket_pre.search(lines):
            lines = curlybracket_pre.sub(r'\1\n}\2', lines)
        while conditional_pre.search(lines):
            lines = conditional_pre.sub(r'\1\n\2', lines)
        # remove all empty lines
        while remove_blanks.search(lines):
            lines = remove_blanks.sub(r'\n', lines)
        lines = conditional_post.sub(r'\1\n\2', lines)
        lines = semicolon_post2.sub(r'\1\n\2', lines)
        # move var statements to its own line
        lines = var_pre.sub(r')\n\1', lines)
        # move dialogue to its own line
        while dialogue_pre.search(lines):
            lines = dialogue_pre.sub(r'\1\n\2', lines)
        # move name tag to its own line
        lines = name_pre.sub(r'\1\n#\2', lines)
        lines = name.sub(r'\1\n\2', lines)
        # add empty lines to improve readability
        lines = dialogue_sep1.sub(r'\1\n\2', lines)
        lines = dialogue_sep2.sub(r')\n\n\1', lines)
        lines = dialogue_sep3.sub(r'\1\n\n', lines)
        # copy line (blank)
        lines = dialogue.sub(r';\1"\2"\n&\1""', lines)
        # set quotes and add blank line in case of voice
        lines = voiced.sub(r'\1「」"\n', lines)
        # keep only one blank line
        while doubles.search(lines):
            lines = doubles.sub(r'\n\n', lines)
        lines = lines.replace("\n", "\r\n")
        fpout.write(lines)
    os.rename(file + ".new", file)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} filename")
        print("You need to specify a file to format")
        sys.exit()
    for file in sys.argv[1:]:
         walk_file(file)

if __name__ == "__main__":
    main()
