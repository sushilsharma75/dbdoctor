import Link from 'next/link';

// T4.4: the public landing page. The hero asset is a real report.

const STEPS = [
  {
    title: '1 · You run one read-only script',
    body: 'Download a single Python file you can read in ten minutes. It opens a read-only session, collects statistics views only, and strips every literal before anything leaves your machine. We never get credentials.',
  },
  {
    title: '2 · Upload the sanitized snapshot',
    body: 'The snapshot is normalized metrics — query digests, table sizes, index usage, settings. No row data, no parameter values, hostnames hashed by default.',
  },
  {
    title: '3 · Get an expert-reviewed report',
    body: 'A deterministic rule engine produces evidence-backed findings; a human reviews every report before you see it. You get a prioritized PDF and paste-ready tickets for your tracker.',
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
    <div className="space-y-16">
      <section className="pt-8">
        <h1 className="max-w-2xl text-4xl leading-tight">
          Find out exactly why your database is slow —{' '}
          <em className="text-rust">without handing anyone your credentials.</em>
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-ink/80">
          dbdoctor turns one sanitized statistics snapshot into a prioritized, evidence-backed
          performance audit for PostgreSQL and MySQL: slow queries, missing and wasted indexes,
          risky settings — each with a concrete, staging-tested fix your team can apply.
        </p>
        <div className="mt-8 flex gap-4">
          <Link
            href="/new-audit"
            className="bg-ink px-6 py-3 text-cream hover:bg-rust"
            data-testid="cta-start"
          >
            Start your audit — $199
          </Link>
          <a href="/samples/sample_pg.pdf" className="border border-ink px-6 py-3 hover:border-rust hover:text-rust">
            Read a sample report
          </a>
        </div>
      </section>

      <section>
        <h2 className="text-2xl">How it works</h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.title} className="border border-ink/15 bg-white p-5">
              <h3 className="font-bold">{s.title}</h3>
              <p className="mt-2 text-sm text-ink/80">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl">See a real report</h2>
        <p className="mt-2 max-w-2xl text-ink/80">
          These are complete sample audits generated from a deliberately misconfigured test
          database — the same document you would receive, with a fictional client name.
        </p>
        <div className="mt-4 flex gap-4">
          <a href="/samples/sample_pg.pdf" className="border border-ink px-5 py-2 hover:text-rust">
            PostgreSQL sample (PDF)
          </a>
          <a href="/samples/sample_mysql.pdf" className="border border-ink px-5 py-2 hover:text-rust">
            MySQL sample (PDF)
          </a>
        </div>
      </section>

      <section>
        <h2 className="text-2xl">Pricing</h2>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <div className="border border-ink bg-white p-6">
            <h3 className="text-xl">One-time audit</h3>
            <p className="mt-1 text-3xl">
              $199 <span className="text-base text-ink/60">/ ₹9,999 incl. GST</span>
            </p>
            <ul className="mt-4 list-inside list-disc space-y-1 text-sm text-ink/80">
              <li>Full report: queries, indexes, config, growth</li>
              <li>Human-reviewed before delivery</li>
              <li>Paste-ready tickets for GitHub / Jira</li>
              <li>30-minute debrief call</li>
            </ul>
          </div>
          <div className="border border-ink/30 bg-white/60 p-6">
            <h3 className="text-xl text-ink/70">Weekly monitoring</h3>
            <p className="mt-1 text-3xl text-ink/50">coming soon</p>
            <p className="mt-4 text-sm text-ink/60">
              The same analysis every Monday morning: what got slower, what changed, what to fix
              next. Audit customers get first access.
            </p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-2xl">Security model, honestly</h2>
        <dl className="mt-6 space-y-5">
          {FAQ.map((f) => (
            <div key={f.q}>
              <dt className="font-bold">{f.q}</dt>
              <dd className="mt-1 max-w-2xl text-sm text-ink/80">{f.a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
