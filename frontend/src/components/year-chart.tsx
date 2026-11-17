"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Row { year: string; count: number }

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{r.year}</strong>: {r.count} confirmed FU publication{r.count === 1 ? "" : "s"}
    </div>
  );
}

/** Single-series column chart: one hue (series-1), no legend (the title names it), table view below. */
export function YearChart({ data }: { data: Row[] }) {
  return (
    <div style={{ width: "100%", height: 240 }} role="img" aria-label="Confirmed Fountain University output by publication year">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -16 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="year" tickLine={false} axisLine={{ stroke: "var(--border-strong)" }}
                 tick={{ fill: "var(--text-3)", fontSize: 12 }} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "var(--text-3)", fontSize: 12 }} />
          <Tooltip content={<Tip />} cursor={{ fill: "var(--surface-2)" }} />
          <Bar dataKey="count" fill="var(--series-1)" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
