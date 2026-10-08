"use client";

import { cn } from "@/services/tech/TailwindS";
import { useEffect, useRef, useState } from "react";
import styles from "./HorizontalReel.module.css";

// ============================================================================
// Types
// ============================================================================

export type HorizontalReelRow = {
  label: string;
  value: string;
  chipTone?: "positive" | "warning" | "critical";
};

export type HorizontalReelCase = {
  id: string;
  photo: string;
  photoAlt?: string;
  objectPosition?: string;
  mark?: { mx: string; my: string };
  tagLeft?: string;
  tagRight?: string;
  rows: HorizontalReelRow[];
};

export interface HorizontalReelProps {
  cases: HorizontalReelCase[];
  replayLabel: string;
  sceneHoldMs?: number;
  className?: string;
}

// ============================================================================
// Private — a one-shot 16:9 reel: each case's photo reveals a marker, then a
// label/value panel, holds, then wipes to the next. Freezes on the last case
// with a floating Replay control. No case count or content is assumed.
// ============================================================================

type SceneState = { markOn: boolean; panelOn: boolean; rowsOn: boolean };

type ReelState = {
  current: number;
  scenes: SceneState[];
  finished: boolean;
  wipe: "idle" | "cover" | "clear";
};

const IDLE_SCENE: SceneState = { markOn: false, panelOn: false, rowsOn: false };
const WIPE_STEP = 230;
const DEFAULT_SCENE_HOLD = 4900;

function initialState(count: number): ReelState {
  return {
    current: 0,
    scenes: Array.from({ length: count }, () => IDLE_SCENE),
    finished: false,
    wipe: "idle",
  };
}

// ============================================================================
// Component
// ============================================================================

function HorizontalReel({
  cases,
  replayLabel,
  sceneHoldMs = DEFAULT_SCENE_HOLD,
  className,
}: HorizontalReelProps) {
  const [state, setState] = useState<ReelState>(() => initialState(cases.length));
  const timeouts = useRef<ReturnType<typeof setTimeout>[]>([]);

  const setScene = (index: number, patch: Partial<SceneState>) => {
    setState((s) => ({
      ...s,
      scenes: s.scenes.map((sc, i) => (i === index ? { ...sc, ...patch } : sc)),
    }));
  };

  const play = () => {
    for (const t of timeouts.current) clearTimeout(t);
    timeouts.current = [];
    setState(initialState(cases.length));

    const schedule = (fn: () => void, delay: number) => {
      timeouts.current.push(setTimeout(fn, delay));
    };

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced) {
      const reducedHold = 2400;
      cases.forEach((_, i) => {
        schedule(
          () => setState((s) => ({ ...s, current: i, scenes: s.scenes.map(() => IDLE_SCENE) })),
          i * reducedHold
        );
        schedule(() => setScene(i, { panelOn: true, rowsOn: true }), i * reducedHold);
      });
      schedule(() => setState((s) => ({ ...s, finished: true })), cases.length * reducedHold);
      return;
    }

    let base = 0;
    cases.forEach((_, i) => {
      const t0 = base;
      schedule(() => setScene(i, { markOn: true }), t0 + 900);
      schedule(() => setScene(i, { panelOn: true }), t0 + 1300);
      schedule(() => setScene(i, { rowsOn: true }), t0 + 1700);

      const isLast = i === cases.length - 1;
      if (!isLast) {
        schedule(() => setState((s) => ({ ...s, wipe: "cover" })), t0 + sceneHoldMs);
        schedule(
          () => setState((s) => ({ ...s, current: i + 1, wipe: "clear" })),
          t0 + sceneHoldMs + WIPE_STEP
        );
        schedule(() => setState((s) => ({ ...s, wipe: "idle" })), t0 + sceneHoldMs + WIPE_STEP * 2);
      } else {
        schedule(() => setState((s) => ({ ...s, finished: true })), t0 + sceneHoldMs);
      }
      base = t0 + sceneHoldMs;
    });
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: play is stable enough for a mount-only run; re-running per render would restart the reel
  useEffect(() => {
    play();
    return () => {
      for (const t of timeouts.current) clearTimeout(t);
    };
  }, []);

  return (
    <div data-slot="horizontal-reel" className={cn(styles.shell, className)}>
      <div className={styles.frame}>
        <span className={`${styles.crop} ${styles.cropTl}`} aria-hidden="true" />
        <span className={`${styles.crop} ${styles.cropTr}`} aria-hidden="true" />
        <span className={`${styles.crop} ${styles.cropBl}`} aria-hidden="true" />
        <span className={`${styles.crop} ${styles.cropBr}`} aria-hidden="true" />

        {cases.map((c, i) => (
          <Scene
            key={c.id}
            caseData={c}
            scene={state.scenes[i] ?? IDLE_SCENE}
            current={state.current === i}
          />
        ))}

        <div
          className={`${styles.wipe} ${state.wipe === "cover" ? styles.wipeCover : ""} ${
            state.wipe === "clear" ? styles.wipeClear : ""
          }`}
          aria-hidden="true"
        />

        {state.finished && (
          <button type="button" className={styles.replayFloat} onClick={play}>
            ↻ {replayLabel}
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Private — scene sub-component
// ============================================================================

function Scene({
  caseData,
  scene,
  current,
}: {
  caseData: HorizontalReelCase;
  scene: SceneState;
  current: boolean;
}) {
  const sceneClass = [
    styles.scene,
    current ? styles.sceneCurrent : "",
    scene.markOn ? styles.markOn : "",
    scene.panelOn ? styles.panelOn : "",
    scene.rowsOn ? styles.rowsOn : "",
  ]
    .filter(Boolean)
    .join(" ");

  const markStyle = caseData.mark
    ? ({ "--mx": caseData.mark.mx, "--my": caseData.mark.my } as React.CSSProperties)
    : undefined;

  return (
    <div className={sceneClass} aria-hidden="true">
      <div className={styles.photoWrap}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className={styles.photo}
          src={caseData.photo}
          alt={caseData.photoAlt ?? ""}
          style={{ objectPosition: caseData.objectPosition ?? "center" }}
        />
        <div className={styles.photoShade} />
      </div>
      {caseData.mark && (
        <span className={styles.pulse} style={markStyle}>
          <span className={styles.pulseRing} />
          <span className={styles.pulseRing} />
          <span className={styles.pulseCore} />
        </span>
      )}
      <div className={styles.panel}>
        {(caseData.tagLeft || caseData.tagRight) && (
          <div className={styles.tagRow}>
            <span className={styles.caseId}>{caseData.tagLeft}</span>
            <span>{caseData.tagRight}</span>
          </div>
        )}
        <div
          className={styles.rows}
          style={{ "--row-count": caseData.rows.length } as React.CSSProperties}
        >
          {caseData.rows.map((row) => (
            <div className={styles.row} key={row.label}>
              <span className={styles.rowK}>{row.label}</span>
              <span className={`${styles.rowV} ${row.chipTone ? styles.chipValue : ""}`}>
                {row.chipTone && (
                  <span className={`${styles.chip} ${styles[`chip_${row.chipTone}`]}`} />
                )}
                {row.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { HorizontalReel };
