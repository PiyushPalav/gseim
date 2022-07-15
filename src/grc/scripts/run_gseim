#!/usr/bin/env python

import os
import sys
import warnings

def run_main():

    script_path = os.path.dirname(os.path.abspath(__file__))
    source_tree_subpath = "/grc/scripts"
    print("Running from source tree")
    print("script ~/gseim_grc/grc/scripts/run_gseim")
    sys.path.insert(1, script_path[:-len(source_tree_subpath)])

    from grc.main import main
    exit(main())

if __name__ == '__main__':
    run_main()
