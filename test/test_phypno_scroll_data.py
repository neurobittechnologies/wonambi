from inspect import stack
from logging import getLogger, INFO
from nose.tools import raises
from numpy.testing import assert_array_equal
from subprocess import check_output


lg = getLogger('phypno')
lg.setLevel(INFO)
git_ver = check_output("git --git-dir=../.git log |  awk 'NR==1' | "
                       "awk '{print $2}'",
                       shell=True).decode('utf-8').strip()
lg.info('phypno ver: ' + git_ver)
lg.info('Module: ' + __name__)

data_dir = '/home/gio/tools/phypno/data'

#-----------------------------------------------------------------------------#


def test_scroll_data():
    lg.info('---\nfunction: ' + stack()[0][3])
    True