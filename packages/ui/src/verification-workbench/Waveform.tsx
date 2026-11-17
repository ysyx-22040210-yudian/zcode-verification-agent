import { useEffect, useMemo, useRef } from "react";

interface Signal {
  name: string;
  values: Array<{ time: number; value: string }>;
}

const FOCUS = [
  "clk", "rst_n", "wr_req", "rd_req", "push", "pop", "count", "full", "empty", "wr_data", "rd_data",
];

function readVcd(text: string) {
  const signals = new Map<string, Signal>();
  let time = 0;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("$var")) {
      const fields = line.split(/\s+/);
      const id = fields[3];
      const name = fields[4];
      if (id && name && !signals.has(id)) signals.set(id, { name, values: [] });
      continue;
    }
    if (line.startsWith("#")) {
      const tick = Number(line.slice(1));
      if (Number.isFinite(tick)) time = tick;
      continue;
    }
    const match = /^(?:b([01xz]+)\s+(.+)|([01xz])(\S+))$/i.exec(line);
    if (!match) continue;
    const id = match[2] ?? match[4];
    const signal = id ? signals.get(id) : undefined;
    const value = match[1] ?? match[3];
    if (signal && value) signal.values.push({ time, value });
  }
  return {
    duration: Math.max(1, time),
    signals: Array.from(signals.values())
      .filter((signal) => signal.values.length > 0)
      .sort((a, b) => priority(a.name) - priority(b.name))
      .slice(0, 12),
  };
}

function priority(name: string): number {
  const index = FOCUS.indexOf(name);
  return index === -1 ? FOCUS.length : index;
}

export function Waveform({ text, label }: Readonly<{ text: string; label: string }>) {
  const shape = useMemo(() => readVcd(text), [text]);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const element = canvas.current;
    const view = element?.getContext("2d");
    if (!element || !view) return;

    const styles = getComputedStyle(element);
    const foreground = styles.getPropertyValue("--color-foreground").trim() || "#35373c";
    const accent = styles.getPropertyValue("--color-brand").trim() || "#5361df";
    view.clearRect(0, 0, element.width, element.height);
    view.font = "12px monospace";
    view.textBaseline = "middle";
    const left = 108;
    const plot = element.width - left - 16;
    shape.signals.forEach(({ name, values }, line) => {
      const row = 23 + line * 29;
      view.fillStyle = foreground;
      view.fillText(name, 4, row);
      view.strokeStyle = accent;
      view.lineWidth = 1.5;
      for (let index = 0; index < values.length; index++) {
        const current = values[index];
        if (!current) continue;
        const next = values[index + 1];
        const nextTime = next?.time ?? shape.duration;
        const start = left + (current.time / shape.duration) * plot;
        const end = left + (nextTime / shape.duration) * plot;
        const height = current.value === "1" ? row - 6 : current.value === "0" ? row + 6 : row;
        view.beginPath();
        view.moveTo(start, height);
        view.lineTo(end, height);
        if (next && current.value.length === 1 && next.value.length === 1) {
          const nextHeight = next.value === "1" ? row - 6 : next.value === "0" ? row + 6 : row;
          view.lineTo(end, nextHeight);
        }
        view.stroke();
        if (current.value.length > 1 && end - start > 30)
          view.fillText(current.value, start + 3, row - 8);
      }
    });
    view.fillStyle = foreground;
    view.fillText("0", left, element.height - 10);
    const end = String(shape.duration);
    view.fillText(end, element.width - 16 - view.measureText(end).width, element.height - 10);
  }, [shape]);

  if (shape.signals.length === 0) return null;
  return (
    <canvas
      ref={canvas}
      width={900}
      height={shape.signals.length * 29 + 30}
      className="w-full rounded-md border border-border bg-background"
      role="img"
      aria-label={label}
    />
  );
}
