import type { StaffRole } from "@/lib/api/generated/model";

/** German names of the staff roles (see the role column of identity.accounts). */
export const STAFF_ROLE_LABELS = {
  owner: "Inhaber",
  staff: "Mitarbeiter",
  packer: "Packer",
} as const satisfies Record<StaffRole, string>;

/**
 * Owner and staff run the shop: catalogue, fairs, eBay and the settings. Packers scan,
 * pick and ship. The backend checks every request itself; this only keeps the Stellwerk
 * from offering what a role cannot use.
 */
export const OFFICE_ROLES: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);
