// screens/settings.tsx — Ajustes (v7: una sección, sin índice)
import * as React from "react";
import { Switch } from "@/components/ui/switch";

export function SettingsScreen({ dailyLimit, quotaWarn, oneKey, onOneKey }: {
  dailyLimit: number; quotaWarn: number; oneKey: boolean; onOneKey: (v: boolean) => void;
}) {
  const eur = dailyLimit.toLocaleString("es-ES", { minimumFractionDigits: 2 }) + " €";
  return (
    <div data-screen-label="Ajustes" className="animate-rise-in mx-auto flex max-w-[820px] flex-col gap-6 px-8 pt-8 pb-14">
      <h1 className="text-[30px] leading-[1.15] font-bold tracking-[-.028em]">Ajustes</h1>
      <section className="bg-card-grad rounded-[18px] border border-sep shadow-card">
        <Row title="Límite de gasto diario" desc="Al alcanzarlo, las tareas nuevas esperan en cola hasta medianoche.">
          <Value>{eur}</Value>
        </Row>
        <Row title="Aviso de cuota" desc="Marca en ámbar cualquier cuenta o límite que lo supere.">
          <Value>{quotaWarn} %</Value>
        </Row>
        <Row title="Atajos de una tecla" desc="N para nueva tarea, ? para la ayuda. Desactívalos si usas lector de pantalla." last>
          <Switch checked={oneKey} onCheckedChange={onOneKey} aria-label="Atajos de una tecla" className="h-[22px] w-[38px] data-[state=checked]:bg-primary-action data-[state=unchecked]:bg-input" />
        </Row>
      </section>
    </div>
  );
}

function Row({ title, desc, last, children }: { title: string; desc: string; last?: boolean; children: React.ReactNode }) {
  return (
    <div className={"flex items-center gap-4 px-4 py-3.5" + (last ? "" : " border-b border-sep")}>
      <div className="flex-1"><div className="font-medium">{title}</div><div className="text-xs text-muted-foreground">{desc}</div></div>
      {children}
    </div>
  );
}
function Value({ children }: { children: React.ReactNode }) {
  return <span className="rounded-[9px] border border-input px-2.5 py-1.5 font-mono">{children}</span>;
}
