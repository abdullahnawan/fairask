import { money, percent, type Report } from "@/lib/api";

const signed = (cents: number) => `${cents >= 0 ? "+" : "−"}${money(Math.abs(cents))}`;
const change = (share: number | null) => (share === null ? "n/a" : `${share >= 0 ? "+" : ""}${percent(share)}`);

export default function ReportView({ report, askingCents }: { report: Report; askingCents: number }) {
  const { valuation: v, verdict, market, costs, investor } = report;
  // Where the asking price sits on the low..high bar, clamped to the ends.
  const span = v.high_cents - v.low_cents || 1;
  const at = (cents: number) => `${Math.min(100, Math.max(0, ((cents - v.low_cents) / span) * 100))}%`;
  const verdictClass = verdict.label.toLowerCase().replace(" ", "-");

  return (
    <article className="report">
      <section>
        <p className={`verdict ${verdictClass}`}>{verdict.label}</p>
        <p className="lead">
          Asking {money(askingCents)} is {money(Math.abs(verdict.gap_cents))} ({percent(Math.abs(verdict.gap_share))})
          {verdict.gap_cents >= 0 ? " above" : " below"} our fair value of <strong>{money(v.fair_cents)}</strong>.
        </p>
        <div className="range" aria-label={`80% fair range ${money(v.low_cents)} to ${money(v.high_cents)}`}>
          <span className="marker fair" style={{ left: at(v.fair_cents) }} title="Fair value" />
          <span className="marker asking" style={{ left: at(askingCents) }} title="Asking" />
        </div>
        <p className="range-labels">
          <span>{money(v.low_cents)}</span>
          <span><i className="key fair" /> fair value <i className="key asking" /> asking</span>
          <span>{money(v.high_cents)}</span>
        </p>
        {report.notes.map((n) => <p key={n} className="note">{n}</p>)}
      </section>

      <section>
        <h2>Why</h2>
        <ul className="reasons">
          {v.reasons.map((r) => (
            <li key={r.text}>
              <span className={r.dollars_cents >= 0 ? "up" : "down"}>{signed(r.dollars_cents)}</span> {r.text}
            </li>
          ))}
        </ul>
        <p className="muted">
          Compared with the CREA benchmark home, {money(v.benchmark_cents)} in {v.benchmark_month}.
          {report.price_per_sqft_cents !== null && report.fair_per_sqft_cents !== null &&
            ` Asking ${money(report.price_per_sqft_cents)}/sq ft against fair ${money(report.fair_per_sqft_cents)}/sq ft.`}
        </p>
      </section>

      {report.red_flags.length > 0 && (
        <section>
          <h2>Red flags</h2>
          <ul>{report.red_flags.map((f) => <li key={f}>{f}</li>)}</ul>
        </section>
      )}

      <section>
        <h2>Market</h2>
        <dl>
          <dt>Benchmark, past year</dt><dd>{change(market.hpi.change_1y)}</dd>
          <dt>Past five years</dt><dd>{change(market.hpi.change_5y)}</dd>
          <dt>From the {market.hpi.peak_month} peak</dt><dd>{change(market.hpi.from_peak)}</dd>
          {market.area && (
            <>
              <dt>{market.area.area}, {market.area.month}</dt>
              <dd>{market.area.balance} (sales to new listings {market.area.snlr}%)</dd>
              <dt>Average days on market</dt><dd>{market.area.avg_days_on_market}</dd>
              <dt>Sold vs asking</dt><dd>{percent(market.area.sale_to_list, 0)}</dd>
            </>
          )}
        </dl>
      </section>

      <section>
        <h2>Cost to own</h2>
        <dl>
          <dt>Down payment</dt><dd>{money(costs.down_payment_cents)}</dd>
          <dt>CMHC insurance</dt><dd>{money(costs.cmhc_premium_cents)}</dd>
          <dt>Mortgage</dt><dd>{money(costs.mortgage_cents)}</dd>
          <dt>Monthly payment</dt><dd><strong>{money(costs.monthly_payment_cents)}</strong></dd>
          <dt>Land transfer tax</dt><dd>{money(costs.land_transfer_tax_cents)}</dd>
          {costs.stress_test && (
            <>
              <dt>Stress test at {percent(costs.stress_test.qualifying_rate, 2)}</dt>
              <dd>
                {costs.stress_test.passes ? "Passes" : "Fails"} (GDS {percent(costs.stress_test.gds)}, TDS{" "}
                {percent(costs.stress_test.tds)})
              </dd>
            </>
          )}
        </dl>
      </section>

      {investor && (
        <section>
          <h2>As a rental</h2>
          <dl>
            <dt>Rent</dt>
            <dd>
              {money(investor.rent_cents)}/mo
              {investor.rent_source !== "you" &&
                ` (CMHC ${investor.rent_source.centre} average, ${investor.rent_source.survey})`}
            </dd>
            <dt>Gross yield</dt><dd>{percent(investor.gross_yield)}</dd>
            <dt>Monthly cash flow</dt><dd className={investor.cash_flow_cents >= 0 ? "up" : "down"}>{signed(investor.cash_flow_cents)}</dd>
          </dl>
          {investor.rent_source !== "you" && (
            <p className="muted">CMHC surveys apartment buildings, so for a house this rent is a floor.</p>
          )}
        </section>
      )}
    </article>
  );
}
