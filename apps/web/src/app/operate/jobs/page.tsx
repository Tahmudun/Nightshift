import Link from 'next/link';

import { JobAdminTable } from '@/components/JobAdminTable';

/**
 * The job table, operationally. Closed jobs included on purpose — see
 * JobAdminTable's own note on why hiding them would defeat the page.
 */
export default function OperateJobsPage() {
  return (
    <div className="space-y-8">
      <section>
        <Link
          href="/operate"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint hover:text-paper"
        >
          ← Operate
        </Link>
        <h1 className="mt-2 text-[22px] font-medium tracking-tight text-paper">Job table</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Every role the pipeline has ever seen, including the ones it has closed. A job leaves
          this list only if a company is deleted — closure is a state, not a deletion, so its
          history stays readable afterwards.
        </p>
      </section>

      <JobAdminTable />
    </div>
  );
}
