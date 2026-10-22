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
        <Button type="button" variant="ghost" size="sm">
          Passwort ändern
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
