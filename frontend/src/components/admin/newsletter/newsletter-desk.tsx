"use client";

import { Panel } from "@/components/admin/panel";
import { ResultPanel } from "@/components/forms/result-panel";
import { PendingNotice } from "@/components/ui/pending-notice";
import {
  useGetNewsletterOverview,
  usePreviewNewsletter,
} from "@/lib/api/generated/admin-newsletter/admin-newsletter";
import type { NewsletterOverviewOut } from "@/lib/api/generated/model";
import { formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";

/** "1. und 15." */
export function issueDays(days: readonly number[]): string {
  const named = days.map((day) => `${day}.`);
  if (named.length <= 1) {
    return named.join("");
  }
  return `${named.slice(0, -1).join(", ")} und ${named.at(-1)}`;
}

/** A date of the API ("2026-12-01") as "1. Dezember 2026". */
function longDate(day: string): string {
  return formatLongDate(new Date(`${day}T12:00:00`));
}

/**
 * The newsletter in the Stellwerk. It goes out by itself on the issue days if new models
 * came into the shop; this page shows who gets it, what goes into the next one and how
 * it looks.
 */
export function NewsletterDesk() {
  const overview = useGetNewsletterOverview();
  const preview = usePreviewNewsletter();

  if (overview.isPending) {
    return <PendingNotice>Newsletter wird geladen …</PendingNotice>;
  }
  if (overview.isError) {
    return (
      <ResultPanel tone="danger" title="Das hat nicht geklappt">
        <p>{errorMessage(overview.error)}</p>
      </ResultPanel>
    );
  }
  const data = overview.data;
  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <div className="space-y-6">
        <Readers data={data} />
        <NextIssue data={data} />
        <PastIssues data={data} />
      </div>
      <Panel title="Vorschau der nächsten Ausgabe">
        {preview.isPending ? (
          <PendingNotice>Vorschau wird erstellt …</PendingNotice>
        ) : preview.isError ? (
          <p className="text-small text-danger">{errorMessage(preview.error)}</p>
        ) : (
          <div className="space-y-4">
            <p className="text-small text-ink-secondary">
              Betreff: <span className="font-medium text-ink">{preview.data.subject}</span>
              {preview.data.sample_owns ? (
                <>
                  <br />
                  Beispiel-Leser:in besitzt „{preview.data.sample_owns}“; danach richten sich die Empfehlungen.
                  Jede:r bekommt eigene, passend zu den eigenen Käufen.
                </>
              ) : null}
            </p>
            <div className="[perspective:1600px]">
              <iframe
                title="Vorschau des Newsletters"
                srcDoc={preview.data.html}
                sandbox=""
                className="h-[56rem] w-full rounded-md border border-line bg-white shadow-[0_24px_48px_-12px_rgba(38,33,30,0.35),0_4px_10px_rgba(38,33,30,0.12)] transition-transform duration-500 [transform:rotateX(2deg)] hover:[transform:rotateX(0deg)]"
              />
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Readers({ data }: { data: NewsletterOverviewOut }) {
  return (
    <Panel title="Leser:innen">
      <dl className="grid grid-cols-2 gap-4">
        <div className="rounded-md bg-canvas p-4 shadow-[inset_0_-3px_0_var(--accent)]">
          <dt className="label-caps text-ink-tertiary">Bestätigt</dt>
          <dd className="mt-1 text-title tabular-nums">{data.confirmed}</dd>
        </div>
        <div className="rounded-md bg-canvas p-4">
          <dt className="label-caps text-ink-tertiary">Unbestätigt</dt>
          <dd className="mt-1 text-title tabular-nums">{data.pending}</dd>
        </div>
      </dl>
      <p className="mt-4 text-small text-ink-secondary">
        Kund:innen bestellen den Newsletter bei der Registrierung oder unter „Mein Konto“ und bestätigen ihn per
        E-Mail. Unbestätigte Anfragen löschen wir nach zwei Wochen.
      </p>
    </Panel>
  );
}

function NextIssue({ data }: { data: NewsletterOverviewOut }) {
  if (data.issue_days.length === 0) {
    return (
      <Panel title="Nächste Ausgabe">
        <p className="text-small text-ink-secondary">
          Der automatische Versand ist aus (MB_NEWSLETTER_DAYS ist leer).
        </p>
      </Panel>
    );
  }
  return (
    <Panel title="Nächste Ausgabe">
      <p>
        {data.next_issue ? (
          <>
            Am <strong>{longDate(data.next_issue)}</strong> ab 9 Uhr
          </>
        ) : (
          "Kein Termin"
        )}
        {data.waiting.length === 0 ? ", aber nur wenn bis dahin neue Modelle in den Shop kommen." : "."}
      </p>
      <p className="mt-2 text-small text-ink-secondary">
        Automatisch am {issueDays(data.issue_days)} jedes Monats, wenn es seit der letzten Ausgabe Neues gibt.
      </p>
      {data.waiting.length > 0 ? (
        <>
          <h3 className="mt-5 label-caps text-ink-tertiary">Neu seit der letzten Ausgabe</h3>
          <ul className="mt-2 space-y-1">
            {data.waiting.map((name) => (
              <li key={name} className="flex items-center gap-2">
                <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
                {name}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Panel>
  );
}

function PastIssues({ data }: { data: NewsletterOverviewOut }) {
  return (
    <Panel title="Bisherige Ausgaben">
      {data.recent.length === 0 ? (
        <p className="text-small text-ink-secondary">Noch keine Ausgabe verschickt.</p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="text-left text-ink-tertiary">
              <th className="pb-2 font-normal">Nr.</th>
              <th className="pb-2 font-normal">Datum</th>
              <th className="pb-2 text-right font-normal">Neue Modelle</th>
              <th className="pb-2 text-right font-normal">Empfänger</th>
            </tr>
          </thead>
          <tbody>
            {data.recent.map((issue) => (
              <tr key={issue.number} className="border-t border-line">
                <td className="py-2 tabular-nums">{issue.number}</td>
                <td className="py-2">{longDate(issue.issue_date)}</td>
                <td className="py-2 text-right tabular-nums">{issue.new_models}</td>
                <td className="py-2 text-right tabular-nums">{issue.sent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
