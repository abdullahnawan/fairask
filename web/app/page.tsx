"use client";

import { useEffect, useState } from "react";
import ListingForm from "@/components/ListingForm";
import PasteImport from "@/components/PasteImport";
import { ReportDetails, ReportSummary } from "@/components/ReportView";
import { evaluate, getOptions, type Options, type Report } from "@/lib/api";
import { emptyForm, toRequest, type Form } from "@/lib/request";

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [form, setForm] = useState<Form>(emptyForm);
  const [report, setReport] = useState<{ report: Report; askingCents: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getOptions().then(setOptions, (e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!report) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById("report")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }, [report]);

  async function submit() {
    setError(null);
    setReport(null);  // never leave the last listing's verdict next to a new error
    setBusy(true);
    try {
      const body = toRequest(form);
      setReport({ report: await evaluate(body), askingCents: body.asking_cents as number });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="wrap">
          <h1>FairAsk</h1>
          <p>Is the asking price fair? Homes in Waterloo Region and the GTA.</p>
        </div>
      </header>
      <div aria-live="polite">
        {report && <ReportSummary report={report.report} askingCents={report.askingCents} />}
      </div>
      <main className={report ? "wrap" : "wrap solo"}>
        {error && <p className="error" role="alert">{error}</p>}
        <div className={report ? "layout" : undefined}>
          <div className="sheet">
            {options ? (
              <>
                <PasteImport cities={options.cities} onParsed={(fields) => setForm((f) => ({ ...f, ...fields }))} />
                <ListingForm form={form} options={options} busy={busy} onChange={setForm} onSubmit={submit} />
              </>
            ) : (
              !error && <p className="empty" aria-busy="true">Loading…</p>
            )}
          </div>
          {report && (
            <div className="sheet">
              <ReportDetails report={report.report} />
            </div>
          )}
        </div>
      </main>
    </>
  );
}
