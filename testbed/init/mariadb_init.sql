-- Grants for the collector account (MariaDB: no sys schema to grant on).
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'dbdoctor'@'%';
GRANT SELECT ON performance_schema.* TO 'dbdoctor'@'%';
FLUSH PRIVILEGES;
