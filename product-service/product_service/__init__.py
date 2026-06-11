try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:
    # SQLite-based tests do not require the MySQL compatibility driver.
    pass
