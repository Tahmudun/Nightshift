/**
 * How a role's enums are written in the interface, in one place.
 *
 * These lived in `JobRow` until the city needed to say the same things about
 * the same role in its detail panel. Two copies of "Policy not stated" is how a
 * list and a map begin to disagree about a job — which is the exact failure
 * §5.6 makes an M4c acceptance criterion, one level below the one it is
 * usually about.
 *
 * The `unknown` cases are the point of the table. A missing employment type
 * renders as "Type not stated", not as a blank and not as "Full time":
 * AMENDMENTS A10's rule for salary is the same rule, and an absent fact
 * presented as a default is a fabricated qualification.
 */

import type { EmploymentType, RemotePolicy } from '@/lib/schemas';

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  full_time: 'Full time',
  part_time: 'Part time',
  internship: 'Internship',
  contract: 'Contract',
  temporary: 'Temporary',
  unknown: 'Type not stated',
};

export const REMOTE_LABELS: Record<RemotePolicy, string> = {
  on_site: 'On site',
  hybrid: 'Hybrid',
  remote: 'Remote',
  unknown: 'Policy not stated',
};
