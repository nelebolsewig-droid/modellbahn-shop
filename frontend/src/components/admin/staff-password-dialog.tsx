"use client";

import { useState } from "react";

import { PasswordChangeForm } from "@/components/forms/password-change-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useChangeStaffPassword } from "@/lib/api/generated/admin-auth/admin-auth";

export function StaffPasswordDialog() {
  const [open, setOpen] = useState(false);
  const changePassword = useChangeStaffPassword();

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="max-sm:px-2.5">
          {/* A key on the phone, where the header has room for little else. */}
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-5 sm:hidden">
            <circle cx="6.5" cy="13.5" r="3.5" />
            <path d="m9 11 7.5-7.5M14 6l2 2M12 8l1.5 1.5" strokeLinecap="round" />
          </svg>
          <span className="max-sm:sr-only">Passwort ändern</span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Passwort ändern</DialogTitle>
        <DialogDescription>
          Du bleibst hier angemeldet; alle anderen Sitzungen deines Zugangs werden beendet.
        </DialogDescription>
        <div className="mt-6">
          {/* Mounted only while open, so a reopened dialog starts empty. */}
          <PasswordChangeForm
            submit={async (values) => {
              await changePassword.mutateAsync({ data: values });
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
