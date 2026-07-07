import Link from 'next/link';

// T4.4: the public landing page, in the POSTMORTEM design language.

const STEPS = [
  {
    n: '01',
    title: 'You run one read-only script',
    body: 'Download a single Python file you can read in ten minutes. It opens a read-only session, collects statistics views only, and strips every literal before anything leaves your machine. We never get credentials.',
  },
  {
    n: '02',
    title: 'Upload the sanitized snapshot',
    body: 'The snapshot is normalized metrics — query digests, table sizes, index usage, settings. No row data, no parameter values, hostnames hashed by default.',
  },
  {
    n: '03',
    title: 'Get an expert-reviewed report',
    body: 'A deterministic rule engine produces prioritized, evidence-backed findings; a human reviews every report before you see it. You get a PDF plus paste-ready tickets for your tracker.',
  },
];

const FAQ = [
  {
    q: 'Do you need access to my database?',
    a: 'No. You run the collector yourself, inside your environment. It connects with a read-only session, reads statistics views only (never table data), and prints its own SHA256 so you can verify exactly what you executed.',
  },
  {
    q: 'What data leaves my environment?',
    a: 'A JSON file of normalized metrics: query shapes with every literal replaced by "?", table and index statistics, and ~25 whitelisted settings. Hostnames are hashed unless you opt out. You can open the file and read every byte before uploading.',
  },
  {
    q: 'Is this automated advice?',
    a: 'The findings are produced by deterministic rules with named numeric evidence — and every report is reviewed by a human before delivery. Recommendations always come with a staging-first test plan; nothing touches your database automatically.',
  },
  {
    q: 'Which engines are supported?',
    a: 'PostgreSQL 13+ (including RDS, Aurora and Cloud SQL) and MySQL 8 / MariaDB. The collector degrades gracefully and tells you exactly how to enable missing statistics.',
  },
  {
    q: 'What does it cost?',
    a: 'A one-time audit is $199 (₹9,999 incl. GST in India). A weekly monitoring subscription is coming soon — audit customers get first access.',
  },
];

export default function Landing() {
  return (
    <div className="space-y-8">
      {/* hero */}
      <section className="bg-grid relative overflow-hidden rounded-lg border border-ink-600/40 p-6 pt-12 md:p-8 md:pt-20">
        <p className="label mb-4">database performance audits · postgresql + mysql</p>
        <h1 className="max-w-3xl text-3xl font-light leading-[1.1] tracking-tightest text-bone-100 md:text-5xl">
          Find out exactly why your database is slow —{' '}
          <span className="text-flag-warning">without handing anyone your credentials.</span>
        </h1>
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-bone-300 md:text-base">
          dbdoctor turns one sanitized statistics snapshot into a prioritized, evidence-backed
          performance audit: slow queries, missing and wasted indexes, risky settings — each with
          a concrete, staging-tested fix your team can apply.
        </p>
        <div className="mt-8 flex flex-wrap gap-3 pb-5">
          <Link href="/new-audit" className="btn btn-primary" data-testid="cta-start">
            Start your audit — $199
          </Link>
          <a href="/samples/sample_pg.pdf" className="btn btn-secondary">
            Read a sample report
          </a>
        </div>
      </section>

      {/* how it works */}
      <section>
        <p className="label mb-3">How it works</p>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="panel p-5">
              <p className="font-mono text-[11px] text-flag-warning">{s.n}</p>
              <h3 className="mt-2 text-sm font-medium text-bone-100">{s.title}</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-bone-400">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* sample reports */}
      <section className="panel p-5 md:p-6">
        <p className="label mb-2">See a real report</p>
        <p className="max-w-2xl text-[13px] leading-relaxed text-bone-400">
          Complete sample audits generated from a deliberately misconfigured test database — the
          same document you would receive, with a fictional client name.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <a href="/samples/sample_pg.pdf" className="btn btn-secondary">
            PostgreSQL sample · PDF
          </a>
          <a href="/samples/sample_mysql.pdf" className="btn btn-secondary">
            MySQL sample · PDF
          </a>
        </div>
      </section>

      {/* pricing */}
      <section>
        <p className="label mb-3">Pricing</p>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="panel border-flag-warning/40 p-5 md:p-6">
            <p className="label">One-time audit</p>
            <p className="mt-2">
              <span className="stat-num">$199</span>
              <span className="ml-2 font-mono text-xs text-bone-400">/ ₹9,999 incl. GST</span>
            </p>
            <ul className="mt-4 space-y-1.5 text-[13px] text-bone-300">
              <li>· Full report: queries, indexes, config, growth</li>
              <li>· Human-reviewed before delivery</li>
              <li>· Paste-ready tickets for GitHub / Jira</li>
              <li>· 30-minute debrief call</li>
            </ul>
          </div>
          <div className="panel p-5 opacity-60 md:p-6">
            <p className="label">Weekly monitoring</p>
            <p className="stat-num mt-2">soon</p>
            <p className="mt-4 text-[13px] leading-relaxed text-bone-400">
              The same analysis every Monday morning: what got slower, what changed, what to fix
              next. Audit customers get first access.
            </p>
          </div>
        </div>
      </section>

      {/* security FAQ */}
      <section className="panel p-5 md:p-6">
        <p className="label mb-4">Security model, honestly</p>
        <dl className="space-y-4">
          {FAQ.map((f) => (
            <div key={f.q} className="border-b border-ink-600/40 pb-4 last:border-0">
              <dt className="text-sm font-medium text-bone-100">{f.q}</dt>
              <dd className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-bone-400">{f.a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
