import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, Easing} from 'remotion';
import {stepFrames, typeFrames, TerminalScene} from './scenes';

const C = {
  bg: '#0b0f17',
  panel: '#121826',
  bar: '#1a2236',
  text: '#e6edf3',
  dim: '#8b98ad',
  ok: '#3ddc97',
  warn: '#ffb454',
  accent: '#6ea8ff',
};

const mono = 'Cascadia Mono, Consolas, "Courier New", monospace';
const sans = '"Segoe UI", Inter, Arial, sans-serif';

export const Terminal: React.FC<{scene: TerminalScene}> = ({scene}) => {
  const frame = useCurrentFrame();

  const headIn = interpolate(frame, [0, 14], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});

  // frame at which each step starts
  const starts: number[] = [];
  let at = 12;
  for (const s of scene.steps) {
    starts.push(at);
    at += stepFrames(s);
  }

  // the step that is showing its note
  let active = 0;
  starts.forEach((s, i) => {
    if (frame >= s) active = i;
  });

  const rows: React.ReactNode[] = [];
  scene.steps.forEach((s, i) => {
    const t = frame - starts[i];
    if (t < 0) return;
    const typed = Math.max(0, t - 8);
    const nChars = Math.min(s.cmd.length, Math.floor((typed / typeFrames(s.cmd)) * s.cmd.length));
    const typing = nChars < s.cmd.length;
    const cursorOn = typing || Math.floor(frame / 15) % 2 === 0;
    const isLast = i === scene.steps.length - 1;
    rows.push(
      <div key={`c${i}`} style={{marginTop: i === 0 ? 0 : 10}}>
        <span style={{color: C.ok}}>PS {scene.shell === 'PowerShell' ? (s.cwd ? `…\\${s.cwd}` : '…') : ''}&gt; </span>
        <span style={{color: C.text}}>{s.cmd.slice(0, nChars)}</span>
        {(typing || (isLast && !s.out) || i === active) && cursorOn ? <span style={{background: C.text, color: C.bg}}>&nbsp;</span> : null}
      </div>,
    );
    const outStart = 8 + typeFrames(s.cmd) + 10;
    (s.out ?? []).forEach((o, j) => {
      if (t >= outStart + j * 9) {
        const a = interpolate(t, [outStart + j * 9, outStart + j * 9 + 6], [0, 1], {extrapolateRight: 'clamp'});
        rows.push(
          <div key={`o${i}-${j}`} style={{color: o.kind === 'ok' ? C.ok : o.kind === 'warn' ? C.warn : C.dim, opacity: a}}>
            {o.t}
          </div>,
        );
      }
    });
  });

  const note = scene.steps[active].note;
  const noteT = frame - starts[active];
  const noteA = interpolate(noteT, [0, 10], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const noteY = interpolate(noteT, [0, 10], [14, 0], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});

  return (
    <AbsoluteFill style={{background: C.bg, fontFamily: sans}}>
      <div style={{position: 'absolute', left: 150, top: 96, opacity: headIn, transform: `translateY(${(1 - headIn) * 16}px)`}}>
        <div style={{color: C.accent, fontSize: 28, letterSpacing: 6, fontWeight: 700}}>{scene.step}</div>
        <div style={{color: C.text, fontSize: 64, fontWeight: 700, marginTop: 6}}>{scene.title}</div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 150,
          top: 270,
          width: 1620,
          height: 560,
          background: C.panel,
          borderRadius: 18,
          overflow: 'hidden',
          boxShadow: '0 30px 80px rgba(0,0,0,.5)',
          opacity: headIn,
        }}
      >
        <div style={{height: 52, background: C.bar, display: 'flex', alignItems: 'center', padding: '0 22px', gap: 10}}>
          {['#ff5f56', '#ffbd2e', '#27c93f'].map((c) => (
            <div key={c} style={{width: 14, height: 14, borderRadius: 7, background: c}} />
          ))}
          <div style={{color: C.dim, fontSize: 20, marginLeft: 18, fontFamily: sans}}>{scene.shell}</div>
        </div>
        <div style={{padding: '26px 34px', fontFamily: mono, fontSize: 28, lineHeight: 1.5, color: C.text}}>{rows}</div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 150,
          top: 880,
          width: 1620,
          color: C.text,
          fontSize: 38,
          fontWeight: 600,
          opacity: noteA,
          transform: `translateY(${noteY}px)`,
          borderLeft: `6px solid ${C.ok}`,
          paddingLeft: 24,
        }}
      >
        {note}
      </div>
    </AbsoluteFill>
  );
};
