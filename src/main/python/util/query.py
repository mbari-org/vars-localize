# query.py (vars-localize)

__author__ = "Kevin Barnard"
__copyright__ = "Copyright 2019, Monterey Bay Aquarium Research Institute"
__credits__ = ["MBARI"]
__license__ = "GPL"
__maintainer__ = "Kevin Barnard"
__email__ = "kbarnard@mbari.org"
__doc__ = '''

VARS querying utility functions.

@author: __author__
@status: __status__
@license: __license__
'''
import jaydebeapi
from util.utils import get_property


def query(sql):
    connection = jaydebeapi.connect(
        'com.microsoft.sqlserver.jdbc.SQLServerDriver',
        get_property('db', 'url'),
        [get_property('db', 'user'), get_property('db', 'pass')],
        'drivers/mssql-jdbc-7.2.2.jre{}.jar'.format(get_property('misc', 'jre_version'))
    )
    cursor = connection.cursor()
    cursor.execute(sql)
    data = cursor.fetchall()
    cursor.close()
    connection.close()
    return data


def query_file(sql_path, *args):
    sql_file = open(sql_path, 'r')
    sql_str = ' '.join([line.strip() for line in sql_file.readlines()])  # Reformat to single-line str
    return query(format_escape_sql(sql_str, args))


def format_escape_sql(sql: str, args):
    return sql.format(*[arg.replace('\'', '\'\'') for arg in args]) if args else sql
