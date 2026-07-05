-- Grants for the collector account, mirroring docs/enable_performance_schema.md:
-- statistics views only, never table data beyond the test schema.
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'dbdoctor'@'%';
GRANT SELECT ON performance_schema.* TO 'dbdoctor'@'%';
GRANT SELECT ON sys.* TO 'dbdoctor'@'%';
-- sys views are SECURITY INVOKER and call sys helper functions internally
GRANT EXECUTE ON sys.* TO 'dbdoctor'@'%';
FLUSH PRIVILEGES;
