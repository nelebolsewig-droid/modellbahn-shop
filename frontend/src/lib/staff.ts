import type { StaffRole } from "@/lib/api/generated/model";

/** German names of the staff roles (see the role column of identity.accounts). */
export const STAFF_ROLE_LABELS = {
  owner: "Inhaber",
  staff: "Mitarbeiter",
  packer: "Packer",
} as const satisfies Record<StaffRole, string>;
