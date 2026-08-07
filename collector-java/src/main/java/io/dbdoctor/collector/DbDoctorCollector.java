package io.dbdoctor.collector;

/*
 * dbdoctor JDBC collector — PostgreSQL, MySQL, and MariaDB.
 *
 * Reads performance STATISTICS VIEWS ONLY and writes a normalized snapshot.json
 * that conforms to the DBDoctor Snapshot schema (engine/models.py). It is the
 * Java counterpart of collector/pg_collect.py and collector/mysql_collect.py:
 * the output is byte-for-byte a valid Snapshot, so the engine, report, and web
 * app consume it unchanged.
 *
 * PRIVACY — what leaves this machine and what never does:
 *   * SQL text is normalized: every string and numeric literal is replaced with
 *     '?' BEFORE it is written to the output file. PostgreSQL pg_stat_statements
 *     and MySQL DIGEST_TEXT are already normalized by the server; this collector
 *     adds a second, defense-in-depth stripping pass of its own. No literal
 *     values, no row data, and no credentials are ever written to the snapshot.
 *   * Host and database names are hashed to a short alias by default
 *     (pass --keep-names to keep them readable).
 *   * The session is opened READ-ONLY and this file contains no
 *     INSERT/UPDATE/DELETE/DDL against your data.
 *   * A 5s per-statement timeout is set so collection can never hang your DB.
 *
 * Requires: JDK 17+. The relevant JDBC driver is bundled in the shaded jar
 * (PostgreSQL, MariaDB Connector/J, MySQL Connector/J).
 *
 * Usage:
 *   java -jar dbdoctor-collector.jar --engine postgres \
 *        --host db.internal --port 5432 --user dbdoctor_ro --database shop \
 *        --password-env DBDOCTOR_DB_PASSWORD --out snapshot.json
 *
 * Verify what you are executing: this program prints its own SHA256 at startup;
 * compare it with the published checksum.
 */

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Array;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class DbDoctorCollector {

    static final String COLLECTOR_VERSION = "0.1.0";
    static final int TOP_QUERIES = 200;
    static final int TOP_TABLES = 100;
    static final int STATEMENT_TIMEOUT_MS = 5000;
    static final double PS = 1e9; // picoseconds per millisecond (perf_schema timers are ps)

    // Performance-relevant PostgreSQL settings (names + values only).
    static final String[] PG_SETTINGS_WHITELIST = {
        "autovacuum", "autovacuum_analyze_scale_factor", "autovacuum_naptime",
        "autovacuum_vacuum_scale_factor", "checkpoint_completion_target", "checkpoint_timeout",
        "default_statistics_target", "effective_cache_size", "effective_io_concurrency", "fsync",
        "idle_in_transaction_session_timeout", "jit", "maintenance_work_mem", "max_connections",
        "max_wal_size", "min_wal_size", "random_page_cost", "seq_page_cost", "shared_buffers",
        "shared_preload_libraries", "statement_timeout", "synchronous_commit", "temp_buffers",
        "track_io_timing", "wal_buffers", "work_mem"
    };

    static final String[] MY_VARIABLES_WHITELIST = {
        "binlog_format", "innodb_buffer_pool_size", "innodb_file_per_table",
        "innodb_flush_log_at_trx_commit", "innodb_flush_method", "innodb_io_capacity",
        "innodb_log_buffer_size", "innodb_log_file_size", "join_buffer_size", "long_query_time",
        "max_connections", "max_heap_table_size", "open_files_limit", "performance_schema",
        "query_cache_size", "query_cache_type", "read_rnd_buffer_size", "skip_name_resolve",
        "slow_query_log", "sort_buffer_size", "sync_binlog", "table_definition_cache",
        "table_open_cache", "thread_cache_size", "tmp_table_size"
    };

    static final String[] MY_STATUS_WHITELIST = {
        "Connections", "Created_tmp_disk_tables", "Created_tmp_tables",
        "Innodb_buffer_pool_read_requests", "Innodb_buffer_pool_reads", "Max_used_connections",
        "Opened_tables", "Threads_connected", "Threads_created", "Uptime"
    };

    // ----------------------------------------------------------------------
    // SQL normalization (mirrors the Python collectors). Order matters.
    // ----------------------------------------------------------------------

    static final Pattern PG_DOLLAR_QUOTED =
        Pattern.compile("\\$(?<tag>[A-Za-z_]*)\\$.*?\\$\\k<tag>\\$", Pattern.DOTALL);
    static final Pattern PG_ESCAPE_STRING = Pattern.compile("[eE]'(?:[^'\\\\]|\\\\.|'')*'");
    static final Pattern SINGLE_QUOTED = Pattern.compile("'(?:[^']|'')*'");
    static final Pattern MY_BACKSLASH_STRING = Pattern.compile("'(?:[^'\\\\]|\\\\.|'')*'");
    static final Pattern MY_DOUBLE_QUOTED = Pattern.compile("\"(?:[^\"\\\\]|\\\\.|\"\")*\"");
    static final Pattern NUMBER =
        Pattern.compile("(?<![\\w$.])[-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?(?![\\w])");
    static final Pattern PG_PARAM_MARKER = Pattern.compile("\\$\\d+\\b");
    static final Pattern IN_LIST =
        Pattern.compile("(?i)(\\b(?:IN|VALUES)\\s*)\\(\\s*\\?(?:\\s*,\\s*\\?)*\\s*\\)");
    static final Pattern MY_IN_LIST_ELLIPSIS = Pattern.compile("\\(\\s*\\?\\s*,\\s*\\.\\.\\.\\s*\\)");
    static final Pattern WHITESPACE = Pattern.compile("\\s+");

    static String normalizePg(String sql) {
        if (sql == null) return "";
        String out = PG_DOLLAR_QUOTED.matcher(sql).replaceAll("?");
        out = PG_ESCAPE_STRING.matcher(out).replaceAll("?");
        out = SINGLE_QUOTED.matcher(out).replaceAll("?");
        out = NUMBER.matcher(out).replaceAll("?");
        out = PG_PARAM_MARKER.matcher(out).replaceAll("?");
        out = IN_LIST.matcher(out).replaceAll("$1(?)");
        return WHITESPACE.matcher(out).replaceAll(" ").trim();
    }

    static String normalizeMy(String sql) {
        if (sql == null) return "";
        String out = MY_BACKSLASH_STRING.matcher(sql).replaceAll("?");
        out = MY_DOUBLE_QUOTED.matcher(out).replaceAll("?");
        out = NUMBER.matcher(out).replaceAll("?");
        out = IN_LIST.matcher(out).replaceAll("$1(?)");
        out = MY_IN_LIST_ELLIPSIS.matcher(out).replaceAll("(?)");
        return WHITESPACE.matcher(out).replaceAll(" ").trim();
    }

    static String sha256Hex(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest(s.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(d.length * 2);
            for (byte b : d) sb.append(Character.forDigit((b >> 4) & 0xf, 16))
                               .append(Character.forDigit(b & 0xf, 16));
            return sb.toString();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    /** sha256 of the normalized statement, first 16 hex chars (for sessions/lock waits). */
    static String digestOfPg(String sql) { return sha256Hex(normalizePg(sql)).substring(0, 16); }
    static String digestOfMy(String sql) { return sha256Hex(normalizeMy(sql)).substring(0, 16); }

    static String hostAlias(String host, String db, boolean keepNames) {
        if (keepNames) return host + "/" + db;
        return sha256Hex(host + "/" + db).substring(0, 12);
    }

    static Double round(double v, int scale) {
        return BigDecimal.valueOf(v).setScale(scale, RoundingMode.HALF_UP).doubleValue();
    }

    // ----------------------------------------------------------------------
    // Minimal JSON writer — no third-party dependency, correct escaping.
    // Accepts Map, List, String, Boolean, Long/Integer, Double, and null.
    // ----------------------------------------------------------------------

    static String toJson(Object o) {
        StringBuilder sb = new StringBuilder();
        writeJson(sb, o, 0);
        sb.append('\n');
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    static void writeJson(StringBuilder sb, Object o, int indent) {
        if (o == null) {
            sb.append("null");
        } else if (o instanceof String s) {
            writeJsonString(sb, s);
        } else if (o instanceof Boolean b) {
            sb.append(b ? "true" : "false");
        } else if (o instanceof Double d) {
            sb.append(new BigDecimal(Double.toString(d)).toPlainString());
        } else if (o instanceof Float f) {
            sb.append(new BigDecimal(Float.toString(f)).toPlainString());
        } else if (o instanceof Number n) { // Long, Integer, BigInteger — emit as integer
            sb.append(n.toString());
        } else if (o instanceof Map<?, ?> map) {
            if (map.isEmpty()) { sb.append("{}"); return; }
            sb.append("{\n");
            int i = 0, n = map.size();
            for (Map.Entry<String, Object> e : ((Map<String, Object>) map).entrySet()) {
                pad(sb, indent + 1);
                writeJsonString(sb, e.getKey());
                sb.append(": ");
                writeJson(sb, e.getValue(), indent + 1);
                if (++i < n) sb.append(',');
                sb.append('\n');
            }
            pad(sb, indent);
            sb.append('}');
        } else if (o instanceof List<?> list) {
            if (list.isEmpty()) { sb.append("[]"); return; }
            sb.append("[\n");
            for (int i = 0; i < list.size(); i++) {
                pad(sb, indent + 1);
                writeJson(sb, list.get(i), indent + 1);
                if (i + 1 < list.size()) sb.append(',');
                sb.append('\n');
            }
            pad(sb, indent);
            sb.append(']');
        } else {
            throw new IllegalArgumentException("cannot serialize " + o.getClass());
        }
    }

    static void pad(StringBuilder sb, int indent) {
        for (int i = 0; i < indent; i++) sb.append("  ");
    }

    static void writeJsonString(StringBuilder sb, String s) {
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                case '\b' -> sb.append("\\b");
                case '\f' -> sb.append("\\f");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        sb.append('"');
    }

    // small ordered-map / list helpers to keep collection code readable
    static Map<String, Object> obj() { return new LinkedHashMap<>(); }
    static Long orNull(ResultSet rs, int idx) throws Exception {
        long v = rs.getLong(idx);
        return rs.wasNull() ? null : v;
    }
    static String tsIso(Timestamp t) { return t == null ? null : t.toInstant().toString(); }

    // ======================================================================
    // PostgreSQL collection
    // ======================================================================

    static Map<String, Object> collectPostgres(Args a) throws Exception {
        String url = "jdbc:postgresql://" + a.host + ":" + a.port + "/" + a.database;
        Properties props = new Properties();
        props.setProperty("user", a.user);
        props.setProperty("password", a.password);
        props.setProperty("ApplicationName", "dbdoctor_collector");
        props.setProperty("readOnly", "true");
        // enforce read-only + a statement timeout at the session level
        props.setProperty("options",
            "-c default_transaction_read_only=on -c statement_timeout=" + STATEMENT_TIMEOUT_MS);

        try (Connection c = DriverManager.getConnection(url, props)) {
            c.setReadOnly(true);
            c.setAutoCommit(true);

            try (Statement s = c.createStatement()) {
                // belt and braces: verify the session really is read-only
                try (ResultSet rs = s.executeQuery("SHOW default_transaction_read_only")) {
                    rs.next();
                    if (!"on".equals(rs.getString(1)))
                        throw new IllegalStateException("session is not read-only; refusing to continue");
                }
            }

            List<String> caps = new ArrayList<>(List.of(
                "table_stats", "index_stats", "lock_waits", "sessions", "config"));
            List<String> notes = new ArrayList<>();
            pgCapabilities(c, caps, notes);

            String serverVersion, dbName;
            Long dbSize;
            try (Statement s = c.createStatement();
                 ResultSet rs = s.executeQuery(
                     "SELECT current_setting('server_version'), current_database(),"
                     + " pg_database_size(current_database())")) {
                rs.next();
                serverVersion = rs.getString(1);
                dbName = rs.getString(2);
                dbSize = orNull(rs, 3);
            }

            Map<String, Object> meta = obj();
            meta.put("engine", "postgres");
            meta.put("version", COLLECTOR_VERSION);
            meta.put("server_version", serverVersion);
            meta.put("collected_at", Instant.now().toString());
            meta.put("host_alias", hostAlias(a.host, dbName, a.keepNames));
            meta.put("is_delta", false);
            meta.put("delta_interval_seconds", null);
            meta.put("db_size_bytes", dbSize);
            meta.put("capabilities", caps);
            meta.put("capability_notes", notes);

            Map<String, Object> snap = obj();
            snap.put("meta", meta);
            snap.put("queries", caps.contains("query_stats") ? pgQueries(c) : new ArrayList<>());
            snap.put("tables", pgTables(c));
            snap.put("indexes", pgIndexes(c));
            snap.put("sessions", pgSessions(c));
            snap.put("lock_waits", pgLockWaits(c));
            snap.put("connections", pgConnections(c));
            snap.put("settings", pgSettings(c));
            return snap;
        }
    }

    static void pgCapabilities(Connection c, List<String> caps, List<String> notes) throws Exception {
        try (Statement s = c.createStatement()) {
            boolean pgssInstalled;
            try (ResultSet rs = s.executeQuery(
                    "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")) {
                rs.next();
                pgssInstalled = rs.getLong(1) > 0;
            }
            if (pgssInstalled) {
                try (ResultSet rs = s.executeQuery("SELECT 1 FROM pg_stat_statements LIMIT 1")) {
                    rs.next();
                    caps.add("query_stats");
                } catch (Exception e) {
                    notes.add("pg_stat_statements extension exists but is not readable by this "
                        + "account; grant the pg_monitor role.");
                }
            } else {
                notes.add("pg_stat_statements not installed; per-query statistics unavailable.");
            }
            try (ResultSet rs = s.executeQuery("SELECT current_setting('track_io_timing')")) {
                rs.next();
                if ("on".equals(rs.getString(1))) caps.add("io_timing");
                else notes.add("track_io_timing is off; I/O timing evidence unavailable (optional).");
            }
        }
    }

    static List<Object> pgQueries(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT queryid::text, query, calls, total_exec_time, mean_exec_time, rows"
            + " FROM pg_stat_statements"
            + " WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())"
            + " ORDER BY total_exec_time DESC LIMIT ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setInt(1, TOP_QUERIES);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> q = obj();
                    q.put("query_digest", rs.getString(1));
                    q.put("normalized_sql", normalizePg(rs.getString(2)));
                    q.put("calls", rs.getLong(3));
                    q.put("total_time_ms", round(rs.getDouble(4), 3));
                    q.put("mean_time_ms", round(rs.getDouble(5), 3));
                    q.put("rows_returned", rs.getLong(6));
                    q.put("rows_examined", null);
                    q.put("full_scan_flag", null);
                    q.put("p95_time_ms", null);
                    q.put("p99_time_ms", null);
                    q.put("calls_per_day", null);
                    q.put("time_per_day_ms", null);
                    q.put("delta_low_confidence", null);
                    out.add(q);
                }
            }
        }
        return out;
    }

    static List<Object> pgTables(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT schemaname, relname, pg_total_relation_size(relid),"
            + " n_live_tup, seq_scan, n_dead_tup, last_autovacuum"
            + " FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setInt(1, TOP_TABLES);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Long live = orNull(rs, 4), dead = orNull(rs, 6);
                    long tuples = (live == null ? 0 : live) + (dead == null ? 0 : dead);
                    Map<String, Object> t = obj();
                    t.put("schema_name", rs.getString(1));
                    t.put("name", rs.getString(2));
                    t.put("size_bytes", rs.getLong(3));
                    t.put("row_estimate", live);
                    t.put("seq_scans", orNull(rs, 5));
                    t.put("full_scan_rows_read", null);
                    t.put("dead_tuple_ratio",
                        tuples > 0 ? round((double) (dead == null ? 0 : dead) / tuples, 4) : null);
                    t.put("last_autovacuum", tsIso(rs.getTimestamp(7)));
                    t.put("data_free_bytes", null);
                    t.put("growth_30d_pct", null);
                    out.add(t);
                }
            }
        }
        return out;
    }

    static List<Object> pgIndexes(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT ui.schemaname || '.' || ui.relname, ui.indexrelname,"
            + " pg_get_indexdef(ui.indexrelid), pg_relation_size(ui.indexrelid), ui.idx_scan,"
            + " ix.indisprimary, ix.indisunique"
            + " FROM pg_stat_user_indexes ui JOIN pg_index ix ON ix.indexrelid = ui.indexrelid"
            + " ORDER BY pg_relation_size(ui.indexrelid) DESC LIMIT 500";
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                boolean isPk = rs.getBoolean(6);
                Long scans = orNull(rs, 5);
                Map<String, Object> ix = obj();
                ix.put("table", rs.getString(1));
                ix.put("name", rs.getString(2));
                ix.put("definition", rs.getString(3));
                ix.put("size_bytes", orNull(rs, 4));
                ix.put("scans", scans);
                ix.put("is_primary", isPk);
                ix.put("is_unique", rs.getBoolean(7));
                ix.put("is_duplicate_candidate", false);
                ix.put("is_unused_candidate", (scans == null || scans == 0) && !isPk);
                out.add(ix);
            }
        }
        return out;
    }

    static List<Object> pgSessions(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT pid, state, query,"
            + " extract(epoch FROM clock_timestamp() - COALESCE(xact_start, query_start))"
            + " FROM pg_stat_activity"
            + " WHERE datname = current_database() AND pid <> pg_backend_pid()";
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                String query = rs.getString(3);
                double age = rs.getDouble(4);
                boolean ageNull = rs.wasNull();
                Map<String, Object> se = obj();
                se.put("session_id", String.valueOf(rs.getLong(1)));
                se.put("state", rs.getString(2));
                se.put("query_digest", query != null ? digestOfPg(query) : null);
                se.put("age_seconds", ageNull ? null : round(age, 3));
                out.add(se);
            }
        }
        return out;
    }

    static List<Object> pgLockWaits(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT w.query, b.query,"
            + " extract(epoch FROM clock_timestamp() - w.query_start) * 1000"
            + " FROM pg_stat_activity w"
            + " JOIN LATERAL unnest(pg_blocking_pids(w.pid)) AS blocking(pid) ON true"
            + " JOIN pg_stat_activity b ON b.pid = blocking.pid"
            + " WHERE w.datname = current_database()";
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                String blockedQ = rs.getString(1); // w.query = the waiter
                String blockerQ = rs.getString(2); // b.query = the blocker
                double waitMs = rs.getDouble(3);
                boolean waitNull = rs.wasNull();
                Map<String, Object> lw = obj();
                lw.put("blocker_digest", blockerQ != null ? digestOfPg(blockerQ) : null);
                lw.put("blocked_digest", blockedQ != null ? digestOfPg(blockedQ) : null);
                lw.put("wait_ms", waitNull ? 0.0 : round(waitMs, 1));
                out.add(lw);
            }
        }
        return out;
    }

    static Map<String, Object> pgConnections(Connection c) throws Exception {
        try (Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(
                 "SELECT (SELECT count(*) FROM pg_stat_activity),"
                 + " current_setting('max_connections')::int")) {
            rs.next();
            Map<String, Object> conn = obj();
            conn.put("current", rs.getLong(1));
            conn.put("peak", null);
            conn.put("max_limit", rs.getLong(2));
            return conn;
        }
    }

    static List<Object> pgSettings(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT name, setting, unit FROM pg_settings WHERE name = ANY(?) ORDER BY name";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            Array arr = c.createArrayOf("text", PG_SETTINGS_WHITELIST);
            ps.setArray(1, arr);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> st = obj();
                    st.put("name", rs.getString(1));
                    st.put("value", rs.getString(2));
                    st.put("unit", rs.getString(3));
                    out.add(st);
                }
            }
        }
        return out;
    }

    // ======================================================================
    // MySQL / MariaDB collection
    // ======================================================================

    static Map<String, Object> collectMysql(Args a) throws Exception {
        boolean mariaDbDriver = "mariadb".equals(a.engine);
        String scheme = mariaDbDriver ? "jdbc:mariadb://" : "jdbc:mysql://";
        String url = scheme + a.host + ":" + a.port + "/" + a.database;
        Properties props = new Properties();
        props.setProperty("user", a.user);
        props.setProperty("password", a.password);
        props.setProperty("connectTimeout", "30000");
        props.setProperty("socketTimeout", "30000");

        try (Connection c = DriverManager.getConnection(url, props)) {
            c.setAutoCommit(true);
            try (Statement s = c.createStatement()) {
                s.execute("SET SESSION TRANSACTION READ ONLY");
                try {
                    s.execute("SET SESSION max_execution_time = " + STATEMENT_TIMEOUT_MS); // MySQL
                } catch (Exception e) {
                    s.execute("SET SESSION max_statement_time = " + (STATEMENT_TIMEOUT_MS / 1000.0)); // MariaDB
                }
                boolean readOnly;
                try (ResultSet rs = s.executeQuery("SELECT @@transaction_read_only")) {
                    rs.next();
                    readOnly = rs.getInt(1) == 1;
                } catch (Exception e) {
                    try (ResultSet rs = s.executeQuery("SELECT @@tx_read_only")) { // older MariaDB
                        rs.next();
                        readOnly = rs.getInt(1) == 1;
                    }
                }
                if (!readOnly)
                    throw new IllegalStateException("session is not read-only; refusing to continue");
            }

            String serverVersion;
            try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery("SELECT VERSION()")) {
                rs.next();
                serverVersion = rs.getString(1);
            }
            boolean isMaria = serverVersion.toLowerCase().contains("mariadb");
            String db = a.database;

            boolean sysAvailable = false;
            if (!isMaria) {
                try (Statement s = c.createStatement();
                     ResultSet rs = s.executeQuery(
                         "SELECT count(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = 'sys'")) {
                    rs.next();
                    sysAvailable = rs.getLong(1) > 0;
                }
            }

            List<String> caps = new ArrayList<>(List.of(
                "table_stats", "index_stats", "sessions", "config", "lock_waits"));
            List<String> notes = new ArrayList<>();
            boolean queryStats = myCapabilities(c, isMaria, sysAvailable, caps, notes);

            boolean hasQuantiles = false;
            if (queryStats) {
                try (Statement s = c.createStatement();
                     ResultSet rs = s.executeQuery(
                         "SELECT count(*) FROM information_schema.COLUMNS"
                         + " WHERE TABLE_SCHEMA = 'performance_schema'"
                         + " AND TABLE_NAME = 'events_statements_summary_by_digest'"
                         + " AND COLUMN_NAME = 'QUANTILE_95'")) {
                    rs.next();
                    hasQuantiles = rs.getLong(1) > 0;
                }
            }

            Map<String, String> variables = fetchKv(c, "SHOW GLOBAL VARIABLES");
            Map<String, String> status = fetchKv(c, "SHOW GLOBAL STATUS");

            Long dbSize;
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT COALESCE(SUM(COALESCE(DATA_LENGTH,0) + COALESCE(INDEX_LENGTH,0)), 0)"
                    + " FROM information_schema.tables WHERE TABLE_SCHEMA = ?")) {
                ps.setString(1, db);
                try (ResultSet rs = ps.executeQuery()) {
                    rs.next();
                    dbSize = rs.getLong(1);
                }
            }

            Map<String, Object> meta = obj();
            meta.put("engine", isMaria ? "mariadb" : "mysql");
            meta.put("version", COLLECTOR_VERSION);
            meta.put("server_version", serverVersion);
            meta.put("collected_at", Instant.now().toString());
            meta.put("host_alias", hostAlias(a.host, db, a.keepNames));
            meta.put("is_delta", false);
            meta.put("delta_interval_seconds", null);
            meta.put("db_size_bytes", dbSize);
            meta.put("capabilities", caps);
            meta.put("capability_notes", notes);

            Map<String, Object> snap = obj();
            snap.put("meta", meta);
            snap.put("queries", queryStats ? myQueries(c, db, hasQuantiles) : new ArrayList<>());
            snap.put("tables", myTables(c, db, sysAvailable));
            snap.put("indexes", myIndexes(c, db, sysAvailable));
            snap.put("sessions", mySessions(c));
            snap.put("lock_waits", myLockWaits(c, isMaria));
            snap.put("connections", myConnections(status, variables));
            snap.put("settings", mySettings(variables, status));
            return snap;
        }
    }

    static boolean myCapabilities(Connection c, boolean isMaria, boolean sysAvailable,
                                  List<String> caps, List<String> notes) throws Exception {
        boolean queryStats = false;
        try (Statement s = c.createStatement()) {
            boolean psOn;
            try (ResultSet rs = s.executeQuery("SELECT @@performance_schema")) {
                rs.next();
                psOn = rs.getInt(1) == 1;
            }
            if (psOn) {
                String digestsEnabled = null;
                boolean readable = true;
                try (ResultSet rs = s.executeQuery(
                        "SELECT ENABLED FROM performance_schema.setup_consumers"
                        + " WHERE NAME = 'statements_digest'")) {
                    if (rs.next()) digestsEnabled = rs.getString(1);
                } catch (Exception e) {
                    readable = false;
                }
                if (!readable) {
                    notes.add("this account cannot read performance_schema; grant SELECT on "
                        + "performance_schema.* (see docs/enable_performance_schema.md). "
                        + "Per-query statistics unavailable.");
                    myIndexCaps(isMaria, sysAvailable, caps, notes);
                    return false;
                }
                if ("YES".equals(digestsEnabled)) {
                    caps.add("query_stats");
                    queryStats = true;
                } else {
                    notes.add("performance_schema is on but the statements_digest consumer is "
                        + "disabled; per-query statistics unavailable (fix steps printed).");
                }
                try (ResultSet rs = s.executeQuery(
                        "SELECT count(*) FROM performance_schema.setup_instruments"
                        + " WHERE NAME LIKE 'statement/%' AND ENABLED = 'NO'")) {
                    rs.next();
                    long disabled = rs.getLong(1);
                    if (queryStats && disabled > 0)
                        notes.add(disabled + " statement instruments are disabled; some statements "
                            + "may be missing from query statistics.");
                }
            } else {
                notes.add("performance_schema = OFF; per-query statistics unavailable. Add "
                    + "performance_schema = ON to my.cnf [mysqld] and restart.");
            }
        }
        myIndexCaps(isMaria, sysAvailable, caps, notes);
        return queryStats;
    }

    static void myIndexCaps(boolean isMaria, boolean sysAvailable,
                            List<String> caps, List<String> notes) {
        if (isMaria) {
            notes.add("MariaDB detected: sys schema advisor views unavailable; unused/"
                + "redundant index detection falls back to definition analysis downstream "
                + "(confidence reduced). Latency percentiles unavailable.");
        } else if (!sysAvailable) {
            notes.add("sys schema not readable; unused/redundant index views skipped.");
        } else {
            caps.add("sys_schema");
        }
    }

    static Map<String, String> fetchKv(Connection c, String sql) throws Exception {
        Map<String, String> m = new LinkedHashMap<>();
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) m.put(rs.getString(1), rs.getString(2));
        }
        return m;
    }

    static List<Object> myQueries(Connection c, String db, boolean hasQuantiles) throws Exception {
        List<Object> out = new ArrayList<>();
        String quantileCols = hasQuantiles ? "QUANTILE_95, QUANTILE_99" : "NULL, NULL";
        String sql = "SELECT DIGEST, DIGEST_TEXT, COUNT_STAR, SUM_TIMER_WAIT, AVG_TIMER_WAIT,"
            + " SUM_ROWS_SENT, SUM_ROWS_EXAMINED,"
            + " SUM_NO_INDEX_USED + SUM_NO_GOOD_INDEX_USED, " + quantileCols
            + " FROM performance_schema.events_statements_summary_by_digest"
            + " WHERE SCHEMA_NAME = ? ORDER BY SUM_TIMER_WAIT DESC LIMIT ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, db);
            ps.setInt(2, TOP_QUERIES);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Long q95 = orNull(rs, 9), q99 = orNull(rs, 10);
                    Map<String, Object> q = obj();
                    q.put("query_digest", rs.getString(1));
                    q.put("normalized_sql", normalizeMy(rs.getString(2)));
                    q.put("calls", rs.getLong(3));
                    q.put("total_time_ms", round(rs.getLong(4) / PS, 3));
                    q.put("mean_time_ms", round(rs.getLong(5) / PS, 3));
                    q.put("rows_returned", rs.getLong(6));
                    q.put("rows_examined", orNull(rs, 7));
                    q.put("full_scan_flag", rs.getLong(8) > 0);
                    q.put("p95_time_ms", q95 != null && q95 != 0 ? round(q95 / PS, 3) : null);
                    q.put("p99_time_ms", q99 != null && q99 != 0 ? round(q99 / PS, 3) : null);
                    q.put("calls_per_day", null);
                    q.put("time_per_day_ms", null);
                    q.put("delta_low_confidence", null);
                    out.add(q);
                }
            }
        }
        return out;
    }

    static List<Object> myTables(Connection c, String db, boolean sysAvailable) throws Exception {
        Map<String, Long> fullScans = new LinkedHashMap<>();
        if (sysAvailable) {
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT object_name, rows_full_scanned"
                    + " FROM sys.schema_tables_with_full_table_scans WHERE object_schema = ?")) {
                ps.setString(1, db);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) fullScans.put(rs.getString(1), orNull(rs, 2));
                }
            }
        }
        List<Object> out = new ArrayList<>();
        String sql = "SELECT TABLE_SCHEMA, TABLE_NAME,"
            + " COALESCE(DATA_LENGTH, 0) + COALESCE(INDEX_LENGTH, 0), TABLE_ROWS, DATA_FREE"
            + " FROM information_schema.tables"
            + " WHERE TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE'"
            + " ORDER BY COALESCE(DATA_LENGTH, 0) + COALESCE(INDEX_LENGTH, 0) DESC LIMIT ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, db);
            ps.setInt(2, TOP_TABLES);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    String name = rs.getString(2);
                    Map<String, Object> t = obj();
                    t.put("schema_name", rs.getString(1));
                    t.put("name", name);
                    t.put("size_bytes", rs.getLong(3));
                    t.put("row_estimate", orNull(rs, 4));
                    t.put("seq_scans", null);
                    t.put("full_scan_rows_read", fullScans.get(name));
                    t.put("dead_tuple_ratio", null);
                    t.put("last_autovacuum", null);
                    t.put("data_free_bytes", orNull(rs, 5));
                    t.put("growth_30d_pct", null);
                    out.add(t);
                }
            }
        }
        return out;
    }

    static List<Object> myIndexes(Connection c, String db, boolean sysAvailable) throws Exception {
        java.util.Set<String> unused = new java.util.HashSet<>();
        java.util.Set<String> redundant = new java.util.HashSet<>();
        if (sysAvailable) {
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT object_name, index_name FROM sys.schema_unused_indexes"
                    + " WHERE object_schema = ?")) {
                ps.setString(1, db);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) unused.add(rs.getString(1) + " " + rs.getString(2));
                }
            }
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT table_name, redundant_index_name FROM sys.schema_redundant_indexes"
                    + " WHERE table_schema = ?")) {
                ps.setString(1, db);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) redundant.add(rs.getString(1) + " " + rs.getString(2));
                }
            }
        }
        List<Object> out = new ArrayList<>();
        String sql = "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,"
            + " GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ', ')"
            + " FROM information_schema.statistics WHERE TABLE_SCHEMA = ?"
            + " GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, db);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    String table = rs.getString(1);
                    String name = rs.getString(2);
                    boolean nonUnique = rs.getLong(3) != 0;
                    String key = table + " " + name;
                    Map<String, Object> ix = obj();
                    ix.put("table", db + "." + table);
                    ix.put("name", name);
                    ix.put("definition", "(" + rs.getString(4) + ")");
                    ix.put("size_bytes", null);
                    ix.put("scans", null);
                    ix.put("is_primary", "PRIMARY".equals(name));
                    ix.put("is_unique", !nonUnique);
                    ix.put("is_duplicate_candidate", redundant.contains(key));
                    ix.put("is_unused_candidate", unused.contains(key) && !"PRIMARY".equals(name));
                    out.add(ix);
                }
            }
        }
        return out;
    }

    static List<Object> mySessions(Connection c) throws Exception {
        List<Object> out = new ArrayList<>();
        String sql = "SELECT ID, STATE, TIME, INFO FROM information_schema.PROCESSLIST"
            + " WHERE ID <> CONNECTION_ID()";
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                String state = rs.getString(2);
                Long age = orNull(rs, 3);
                String info = rs.getString(4);
                Map<String, Object> se = obj();
                se.put("session_id", String.valueOf(rs.getLong(1)));
                se.put("state", (state == null || state.isEmpty()) ? null : state);
                se.put("query_digest", info != null ? digestOfMy(info) : null);
                se.put("age_seconds", age != null ? age.doubleValue() : null);
                out.add(se);
            }
        }
        return out;
    }

    static List<Object> myLockWaits(Connection c, boolean isMaria) throws Exception {
        String sql = isMaria
            ? "SELECT b.trx_query, r.trx_query,"
                + " TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) * 1000"
                + " FROM information_schema.INNODB_LOCK_WAITS w"
                + " JOIN information_schema.INNODB_TRX b ON b.trx_id = w.blocking_trx_id"
                + " JOIN information_schema.INNODB_TRX r ON r.trx_id = w.requesting_trx_id"
            : "SELECT blocking_query, waiting_query, wait_age_secs * 1000"
                + " FROM sys.innodb_lock_waits";
        List<Object> out = new ArrayList<>();
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                String blockerQ = rs.getString(1);
                String blockedQ = rs.getString(2);
                double waitMs = rs.getDouble(3);
                boolean waitNull = rs.wasNull();
                Map<String, Object> lw = obj();
                lw.put("blocker_digest", blockerQ != null ? digestOfMy(blockerQ) : null);
                lw.put("blocked_digest", blockedQ != null ? digestOfMy(blockedQ) : null);
                lw.put("wait_ms", waitNull ? 0.0 : round(waitMs, 1));
                out.add(lw);
            }
        } catch (Exception e) {
            // lock-wait views can be absent/unreadable; a degraded run, not a crash
            return new ArrayList<>();
        }
        return out;
    }

    static Map<String, Object> myConnections(Map<String, String> status, Map<String, String> variables) {
        Map<String, Object> conn = obj();
        conn.put("current", Long.parseLong(status.getOrDefault("Threads_connected", "0")));
        conn.put("peak", status.containsKey("Max_used_connections")
            ? Long.parseLong(status.get("Max_used_connections")) : null);
        conn.put("max_limit", Long.parseLong(variables.getOrDefault("max_connections", "0")));
        return conn;
    }

    static List<Object> mySettings(Map<String, String> variables, Map<String, String> status) {
        List<Object> out = new ArrayList<>();
        for (String name : MY_VARIABLES_WHITELIST) {
            if (variables.containsKey(name)) {
                Map<String, Object> st = obj();
                st.put("name", name);
                st.put("value", variables.get(name));
                st.put("unit", null);
                out.add(st);
            }
        }
        for (String name : MY_STATUS_WHITELIST) {
            if (status.containsKey(name)) {
                Map<String, Object> st = obj();
                st.put("name", name);
                st.put("value", status.get(name));
                st.put("unit", null);
                out.add(st);
            }
        }
        return out;
    }

    // ======================================================================
    // CLI
    // ======================================================================

    static final class Args {
        String engine, host = "127.0.0.1", user = "", password = "", database = "";
        int port = -1;
        String out = "snapshot.json";
        boolean keepNames = false;
        boolean selftest = false;
    }

    static int defaultPort(String engine) {
        return "postgres".equals(engine) ? 5432 : 3306;
    }

    public static void main(String[] argv) {
        System.out.println("dbdoctor java collector " + COLLECTOR_VERSION
            + "  sha256(class)=" + classDigest());

        Args a;
        try {
            a = parseArgs(argv);
        } catch (IllegalArgumentException e) {
            System.err.println("error: " + e.getMessage());
            System.err.println(USAGE);
            System.exit(2);
            return;
        }

        try {
            Map<String, Object> snapshot;
            if (a.selftest) {
                snapshot = selftestSnapshot();
            } else if ("postgres".equals(a.engine)) {
                snapshot = collectPostgres(a);
            } else {
                snapshot = collectMysql(a);
            }
            Files.writeString(Path.of(a.out), toJson(snapshot), StandardCharsets.UTF_8);

            @SuppressWarnings("unchecked")
            Map<String, Object> meta = (Map<String, Object>) snapshot.get("meta");
            @SuppressWarnings("unchecked")
            List<String> caps = (List<String>) meta.get("capabilities");
            int nq = ((List<?>) snapshot.get("queries")).size();
            int nt = ((List<?>) snapshot.get("tables")).size();
            System.out.println("wrote " + a.out + "  (queries=" + nq + ", tables=" + nt
                + ", capabilities=" + String.join(",", caps) + ")");
            if (!caps.contains("query_stats"))
                System.out.println("warning: snapshot written with reduced capabilities "
                    + "(per-query statistics unavailable - enable pg_stat_statements / "
                    + "performance_schema statement digests).");
            @SuppressWarnings("unchecked")
            List<String> notes = (List<String>) meta.get("capability_notes");
            for (String n : notes) System.out.println("note: " + n);
        } catch (Exception e) {
            System.err.println("error: collection failed: " + e.getMessage());
            System.exit(1);
        }
    }

    static Args parseArgs(String[] argv) {
        Args a = new Args();
        for (int i = 0; i < argv.length; i++) {
            String k = argv[i];
            switch (k) {
                case "--engine" -> a.engine = req(argv, ++i, k);
                case "--host" -> a.host = req(argv, ++i, k);
                case "--port" -> a.port = Integer.parseInt(req(argv, ++i, k));
                case "--user" -> a.user = req(argv, ++i, k);
                case "--password" -> a.password = req(argv, ++i, k);
                case "--password-env" -> {
                    String env = req(argv, ++i, k);
                    a.password = System.getenv(env);
                    if (a.password == null)
                        throw new IllegalArgumentException("env var " + env + " is not set");
                }
                case "--database" -> a.database = req(argv, ++i, k);
                case "--out" -> a.out = req(argv, ++i, k);
                case "--keep-names" -> a.keepNames = true;
                case "--selftest" -> a.selftest = true;
                case "-h", "--help" -> { System.out.println(USAGE); System.exit(0); }
                default -> throw new IllegalArgumentException("unknown argument: " + k);
            }
        }
        if (a.selftest) return a;
        if (a.engine == null || !(a.engine.equals("postgres") || a.engine.equals("mysql")
                || a.engine.equals("mariadb")))
            throw new IllegalArgumentException("--engine must be one of: postgres, mysql, mariadb");
        if (a.database.isEmpty()) throw new IllegalArgumentException("--database is required");
        if (a.user.isEmpty()) throw new IllegalArgumentException("--user is required");
        if (a.port < 0) a.port = defaultPort(a.engine);
        return a;
    }

    static String req(String[] argv, int i, String key) {
        if (i >= argv.length) throw new IllegalArgumentException("missing value for " + key);
        return argv[i];
    }

    static final String USAGE = """
        dbdoctor JDBC collector — writes a normalized snapshot.json for DBDoctor.

        Usage:
          java -jar dbdoctor-collector.jar --engine <postgres|mysql|mariadb> \\
               --host HOST --port PORT --user USER --database DB \\
               [--password PASS | --password-env VAR] [--out FILE] [--keep-names]

        Options:
          --engine        postgres | mysql | mariadb (required)
          --host          database host (default 127.0.0.1)
          --port          database port (default 5432 for postgres, 3306 otherwise)
          --user          database user (required)
          --database      database/schema name to audit (required)
          --password      password (avoid on shared hosts; prefer --password-env)
          --password-env  name of an environment variable holding the password
          --out           output file (default snapshot.json)
          --keep-names    keep readable host/db names instead of hashing to an alias
          --selftest      write a representative snapshot with no database connection
          -h, --help      show this help

        The collector reads statistics views only, never your table data, opens a
        read-only session, and strips SQL literals before writing the snapshot.""";

    /** SHA256 of the loaded class file, so a customer can verify the running bytecode. */
    static String classDigest() {
        try (var in = DbDoctorCollector.class.getResourceAsStream("DbDoctorCollector.class")) {
            if (in == null) return "unavailable";
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            byte[] d = md.digest();
            StringBuilder sb = new StringBuilder();
            for (byte b : d) sb.append(Character.forDigit((b >> 4) & 0xf, 16))
                               .append(Character.forDigit(b & 0xf, 16));
            return sb.toString();
        } catch (Exception e) {
            return "unavailable";
        }
    }

    // ======================================================================
    // --selftest: build a representative snapshot with no DB, to prove the
    // output conforms to the Snapshot schema (used by conformance tests).
    // ======================================================================

    static Map<String, Object> selftestSnapshot() {
        Map<String, Object> meta = obj();
        meta.put("engine", "postgres");
        meta.put("version", COLLECTOR_VERSION);
        meta.put("server_version", "15.6");
        meta.put("collected_at", Instant.now().toString());
        meta.put("host_alias", hostAlias("selftest-host", "shop", false));
        meta.put("is_delta", false);
        meta.put("delta_interval_seconds", null);
        meta.put("db_size_bytes", 1_200_000_000L);
        meta.put("capabilities", new ArrayList<>(List.of(
            "table_stats", "index_stats", "lock_waits", "sessions", "config", "query_stats")));
        meta.put("capability_notes", new ArrayList<>());

        List<Object> queries = new ArrayList<>();
        Map<String, Object> q = obj();
        q.put("query_digest", "1234567890123456");
        q.put("normalized_sql", normalizePg(
            "SELECT id, status FROM orders WHERE customer_id = 84213 AND status = 'shipped'"));
        q.put("calls", 500_000L);
        q.put("total_time_ms", round(9_000_000.0, 3));
        q.put("mean_time_ms", round(18.0, 3));
        q.put("rows_returned", 500_000L);
        q.put("rows_examined", null);
        q.put("full_scan_flag", null);
        q.put("p95_time_ms", null);
        q.put("p99_time_ms", null);
        q.put("calls_per_day", null);
        q.put("time_per_day_ms", null);
        q.put("delta_low_confidence", null);
        queries.add(q);

        List<Object> tables = new ArrayList<>();
        Map<String, Object> t = obj();
        t.put("schema_name", "public");
        t.put("name", "orders");
        t.put("size_bytes", 2_000_000_000L);
        t.put("row_estimate", 40_000_000L);
        t.put("seq_scans", 5000L);
        t.put("full_scan_rows_read", null);
        t.put("dead_tuple_ratio", round(0.25, 4));
        t.put("last_autovacuum", null);
        t.put("data_free_bytes", null);
        t.put("growth_30d_pct", null);
        tables.add(t);

        List<Object> indexes = new ArrayList<>();
        Map<String, Object> ix = obj();
        ix.put("table", "public.orders");
        ix.put("name", "orders_pkey");
        ix.put("definition", "CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)");
        ix.put("size_bytes", 100_000_000L);
        ix.put("scans", 1_000_000L);
        ix.put("is_primary", true);
        ix.put("is_unique", true);
        ix.put("is_duplicate_candidate", false);
        ix.put("is_unused_candidate", false);
        indexes.add(ix);

        Map<String, Object> connections = obj();
        connections.put("current", 42L);
        connections.put("peak", null);
        connections.put("max_limit", 100L);

        List<Object> settings = new ArrayList<>();
        Map<String, Object> s1 = obj();
        s1.put("name", "shared_buffers");
        s1.put("value", "16384");
        s1.put("unit", "8kB");
        settings.add(s1);

        Map<String, Object> snap = obj();
        snap.put("meta", meta);
        snap.put("queries", queries);
        snap.put("tables", tables);
        snap.put("indexes", indexes);
        snap.put("sessions", new ArrayList<>());
        snap.put("lock_waits", new ArrayList<>());
        snap.put("connections", connections);
        snap.put("settings", settings);
        return snap;
    }
}
