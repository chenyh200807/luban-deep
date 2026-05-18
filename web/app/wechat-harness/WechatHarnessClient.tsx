"use client";

/* eslint-disable i18n/no-literal-ui-text */

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  History,
  MonitorSmartphone,
  Play,
  RotateCcw,
  Smartphone,
} from "lucide-react";

import type {
  HarnessMode,
  HarnessRenderState,
  WechatHarnessCase,
} from "@/lib/wechat-harness-types";
import MarkdownRenderer from "@/components/common/MarkdownRenderer";
import styles from "./wechat-harness.module.css";

type McqSelection = Record<string, string>;

interface WechatHarnessClientProps {
  cases: WechatHarnessCase[];
}

function textFromNodes(nodes: unknown): string {
  if (!Array.isArray(nodes)) return "";
  return nodes
    .map((node) => {
      if (!node || typeof node !== "object") return "";
      const typedNode = node as { children?: unknown; text?: unknown };
      const text = typedNode.text;
      if (text) return String(text);
      return textFromNodes(typedNode.children);
    })
    .join("");
}

function blockText(block: Record<string, unknown>): string {
  const richText = textFromNodes(block.nodes || block.content || block.children);
  if (richText) return richText;
  const direct = block.text || block.title || block.summary || block.detail || block.raw;
  if (direct) return String(direct);
  return "";
}

function asBlocks(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    : [];
}

function asCells(value: unknown): Array<Array<Record<string, unknown>>> {
  return Array.isArray(value)
    ? value.map((row) => asBlocks(row))
    : [];
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function stateForMode(
  currentCase: WechatHarnessCase,
  mode: HarnessMode,
  frameIndex: number,
): HarnessRenderState {
  if (mode === "history") return currentCase.historyState;
  if (mode === "final") return currentCase.finalState;
  return currentCase.streamFrames[Math.min(frameIndex, currentCase.streamFrames.length - 1)].state;
}

function CasePill({ children }: { children: React.ReactNode }) {
  return <span className={styles.casePill}>{children}</span>;
}

function TableBlock({ block }: { block: Record<string, unknown> }) {
  const headers = asBlocks(block.headers);
  const rows = asCells(block.rows);
  const compact = block.mobileStrategy === "compact_cards";

  if (compact) {
    return (
      <section className={styles.structuredBlock} data-block-type="table">
        {block.caption ? <div className={styles.blockCaption}>{String(block.caption)}</div> : null}
        <div className={styles.compactTable}>
          {rows.map((row, rowIndex) => (
            <div className={styles.compactTableRow} key={`row-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <div className={styles.compactCell} key={`cell-${rowIndex}-${cellIndex}`}>
                  <span>{blockText(headers[cellIndex] || { text: `列 ${cellIndex + 1}` })}</span>
                  <strong data-highlight={cell.highlight ? "true" : "false"}>{blockText(cell)}</strong>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className={styles.structuredBlock} data-block-type="table">
      {block.caption ? <div className={styles.blockCaption}>{String(block.caption)}</div> : null}
      <div className={styles.tableScroller}>
        <table className={styles.table}>
          <thead>
            <tr>
              {headers.map((header, index) => (
                <th key={`h-${index}`}>{blockText(header)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`tr-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`td-${rowIndex}-${cellIndex}`} data-highlight={cell.highlight ? "true" : "false"}>
                    {blockText(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FormulaBlock({ block }: { block: Record<string, unknown> }) {
  return (
    <section className={styles.formulaBlock} data-block-type={String(block.type || "formula")}>
      <span>{String(block.displayText || block.latex || "公式")}</span>
      {block.copyText || block.latex ? (
        <code>{String(block.copyText || block.latex)}</code>
      ) : null}
    </section>
  );
}

function StepsBlock({ block }: { block: Record<string, unknown> }) {
  const steps = asBlocks(block.steps);
  return (
    <section className={styles.structuredBlock} data-block-type="steps">
      <div className={styles.blockTitle}>{String(block.title || "步骤")}</div>
      <ol className={styles.stepList}>
        {steps.map((step, index) => (
          <li key={`step-${index}`}>
            <span>{String(step.index || index + 1)}</span>
            <div>
              <strong>{String(step.title || `步骤 ${index + 1}`)}</strong>
              {step.detail ? <p>{String(step.detail)}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecapBlock({ block }: { block: Record<string, unknown> }) {
  return (
    <section className={styles.structuredBlock} data-block-type="recap">
      <div className={styles.blockTitle}>{String(block.title || "本节课总结")}</div>
      {block.summary ? <p className={styles.blockSummary}>{String(block.summary)}</p> : null}
      <ul className={styles.tightList}>
        {asStrings(block.bullets).map((bullet, index) => (
          <li key={`bullet-${index}`}>{bullet}</li>
        ))}
      </ul>
    </section>
  );
}

function ChartBlock({ block }: { block: Record<string, unknown> }) {
  const fallback = block.fallbackTable || block.fallback_table;
  const series = asBlocks(block.series);
  return (
    <section className={styles.structuredBlock} data-block-type="chart">
      <div className={styles.blockTitle}>{String(block.title || "数据图表")}</div>
      {block.summary ? <p className={styles.blockSummary}>{String(block.summary)}</p> : null}
      <div className={styles.chartBars}>
        {series.map((item, index) => {
          const value = String(item.value || item.y || asStrings(item.values)[0] || index + 1);
          const width = Math.max(16, Math.min(100, Number.parseFloat(value) * 12 || 42));
          return (
            <div className={styles.chartRow} key={`series-${index}`}>
              <span>{String(item.name || item.label || `数据 ${index + 1}`)}</span>
              <i style={{ width: `${width}%` }} />
              <strong>{value}</strong>
            </div>
          );
        })}
      </div>
      {fallback && typeof fallback === "object" ? (
        <TableBlock block={fallback as Record<string, unknown>} />
      ) : null}
    </section>
  );
}

function MarkdownBlock({ block }: { block: Record<string, unknown> }) {
  const type = String(block.type || "paragraph");
  if (type === "blank") return null;
  if (type === "callout") {
    return (
      <section className={styles.callout} data-variant={String(block.variant || "highlight")}>
        <strong>{String(block.label || "提示")}</strong>
        <span>{blockText(block)}</span>
      </section>
    );
  }
  if (type === "ul" || type === "ol") {
    const items = asBlocks(block.items);
    const ListTag = type === "ol" ? "ol" : "ul";
    return (
      <ListTag className={styles.markdownList}>
        {items.map((item, index) => (
          <li key={`li-${index}`}>{blockText(item)}</li>
        ))}
      </ListTag>
    );
  }
  if (type.startsWith("h")) {
    return <h3 className={styles.markdownHeading}>{blockText(block)}</h3>;
  }
  return <p className={styles.markdownParagraph}>{blockText(block)}</p>;
}

function RenderBlock({ block }: { block: Record<string, unknown> }) {
  const type = String(block.type || "");
  if (type === "table") return <TableBlock block={block} />;
  if (type === "formula_block" || type === "formula_inline") return <FormulaBlock block={block} />;
  if (type === "steps") return <StepsBlock block={block} />;
  if (type === "recap" || type === "summary") return <RecapBlock block={block} />;
  if (type === "chart") return <ChartBlock block={block} />;
  return <MarkdownBlock block={block} />;
}

function McqCards({
  cards,
  hint,
  selections,
  onSelect,
  submitted,
  onSubmit,
}: {
  cards: Array<Record<string, unknown>>;
  hint: string;
  selections: McqSelection;
  submitted: boolean;
  onSelect: (questionId: string, option: string) => void;
  onSubmit: () => void;
}) {
  if (!cards.length) return null;

  return (
    <section className={styles.mcqSection} data-testid="mcq-section">
      {cards.map((card, index) => {
        const questionId = String(card.questionId || `q-${index}`);
        const options = asBlocks(card.options);
        return (
          <article className={styles.mcqCard} key={questionId}>
            <div className={styles.mcqStem}>
              <span>题目 {String(card.index || index + 1)}</span>
              <strong>{String(card.stem || "请选择正确选项")}</strong>
            </div>
            <div className={styles.optionGrid}>
              {options.map((option) => {
                const key = String(option.key || "");
                const selected = selections[questionId] === key;
                return (
                  <button
                    className={styles.optionButton}
                    data-testid="mcq-option"
                    data-selected={selected ? "true" : "false"}
                    key={`${questionId}-${key}`}
                    onClick={() => onSelect(questionId, key)}
                    type="button"
                  >
                    <span>{key}</span>
                    <strong>{String(option.text || "")}</strong>
                  </button>
                );
              })}
            </div>
          </article>
        );
      })}
      <div className={styles.mcqFooter}>
        <span>{hint || "请选择后提交答案"}</span>
        <button data-testid="mcq-submit" onClick={onSubmit} type="button">
          提交
        </button>
      </div>
      <div className={styles.mcqStatus} data-testid="mcq-status">
        {submitted
          ? `已记录选择：${Object.values(selections).join(", ") || "空"}`
          : "等待作答"}
      </div>
    </section>
  );
}

function PhonePreview({
  state,
  currentCase,
  mode,
  frameLabel,
}: {
  state: HarnessRenderState;
  currentCase: WechatHarnessCase;
  mode: HarnessMode;
  frameLabel: string;
}) {
  const [selections, setSelections] = useState<McqSelection>({});
  const [submitted, setSubmitted] = useState(false);
  const blocks = state.blocks || [];
  const mcqCards = state.mcqCards || [];

  return (
    <section className={styles.phoneShell} data-testid="phone-shell">
      <div className={styles.phoneTopbar}>
        <span>鲁班智考</span>
        <strong>{mode === "stream" ? frameLabel : mode === "history" ? "历史恢复" : "最终态"}</strong>
      </div>
      <div className={styles.phoneScreen} data-testid="phone-screen">
        <article className={styles.userBubble}>请按建筑实务考试场景回答。</article>
        <article className={styles.aiBubble}>
          <header>
            <span>AI 批改助手</span>
            <i data-phase={state.streamPhase}>{state.streamPhase}</i>
          </header>
          {blocks.length ? (
            <div className={styles.blockStack} data-testid="render-block-stack">
              {blocks.map((block, index) => (
                <RenderBlock block={block} key={`${String(block.type || "block")}-${index}`} />
              ))}
            </div>
          ) : state.renderableContent ? (
            <MarkdownRenderer
              className={styles.markdownFallback}
              content={state.renderableContent}
              variant="compact"
            />
          ) : null}
          <McqCards
            cards={mcqCards}
            hint={state.mcqHint}
            onSelect={(questionId, option) => {
              setSelections((current) => ({ ...current, [questionId]: option }));
              setSubmitted(false);
            }}
            onSubmit={() => setSubmitted(true)}
            selections={selections}
            submitted={submitted}
          />
          {state.originalContent ? (
            <details className={styles.originalToggle}>
              <summary>查看原文</summary>
              <MarkdownRenderer content={state.originalContent} variant="compact" />
            </details>
          ) : null}
          {!blocks.length && !state.renderableContent && !mcqCards.length ? (
            <p className={styles.emptyRender}>当前帧没有可见内容。</p>
          ) : null}
        </article>
      </div>
      <div className={styles.phoneInput}>
        <span>{currentCase.surface}</span>
        <p>输入你的问题或答案...</p>
      </div>
    </section>
  );
}

export default function WechatHarnessClient({ cases }: WechatHarnessClientProps) {
  const [caseIndex, setCaseIndex] = useState(0);
  const [mode, setMode] = useState<HarnessMode>("final");
  const [frameIndex, setFrameIndex] = useState(0);
  const currentCase = cases[caseIndex];
  const frameLabel = currentCase.streamFrames[Math.min(frameIndex, currentCase.streamFrames.length - 1)].label;
  const state = stateForMode(currentCase, mode, frameIndex);
  const allTags = useMemo(
    () => Array.from(new Set(cases.flatMap((item) => item.tags))).slice(0, 12),
    [cases],
  );

  function selectCase(index: number) {
    setCaseIndex(index);
    setFrameIndex(0);
    setMode("final");
  }

  function advanceFrame() {
    setMode("stream");
    setFrameIndex((current) => (current + 1) % currentCase.streamFrames.length);
  }

  return (
    <main className={styles.root} data-testid="wechat-harness-root">
      <aside className={styles.sidebar}>
        <div className={styles.brandRow}>
          <MonitorSmartphone size={19} />
          <div>
            <strong>微信小程序影子测试</strong>
            <span>{cases.length} 个 contract cases</span>
          </div>
        </div>
        <div className={styles.tagRail}>
          {allTags.map((tag) => (
            <CasePill key={tag}>{tag}</CasePill>
          ))}
        </div>
        <div className={styles.caseList} data-testid="harness-case-list">
          {cases.map((item, index) => (
            <button
              aria-current={index === caseIndex ? "true" : undefined}
              className={styles.caseButton}
              data-testid="harness-case-button"
              key={item.id}
              onClick={() => selectCase(index)}
              type="button"
            >
              <span>{item.title}</span>
              <small>{item.sourcePath}</small>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      </aside>

      <section className={styles.workbench}>
        <header className={styles.toolbar}>
          <div>
            <span className={styles.surfaceLabel}>{currentCase.surface}</span>
            <h1>{currentCase.title}</h1>
            <p>{currentCase.description}</p>
          </div>
          <div className={styles.modeTabs} role="tablist" aria-label="Harness modes">
            <button
              data-selected={mode === "stream" ? "true" : "false"}
              data-testid="harness-mode-stream"
              onClick={() => setMode("stream")}
              type="button"
            >
              <Play size={15} />
              实时流式
            </button>
            <button
              data-selected={mode === "final" ? "true" : "false"}
              data-testid="harness-mode-final"
              onClick={() => setMode("final")}
              type="button"
            >
              <Smartphone size={15} />
              最终态
            </button>
            <button
              data-selected={mode === "history" ? "true" : "false"}
              data-testid="harness-mode-history"
              onClick={() => setMode("history")}
              type="button"
            >
              <History size={15} />
              历史 hydrate
            </button>
          </div>
        </header>

        <div className={styles.mainGrid}>
          <div className={styles.previewColumn}>
            <div className={styles.replayControls}>
              <button onClick={advanceFrame} type="button">
                <Play size={15} />
                下一帧
              </button>
              <button
                onClick={() => {
                  setMode("stream");
                  setFrameIndex(0);
                }}
                type="button"
              >
                <RotateCcw size={15} />
                重播
              </button>
              <div className={styles.frameDots}>
                {currentCase.streamFrames.map((frame, index) => (
                  <button
                    aria-label={frame.label}
                    aria-current={mode === "stream" && index === frameIndex ? "true" : undefined}
                    key={frame.id}
                    onClick={() => {
                      setMode("stream");
                      setFrameIndex(index);
                    }}
                    type="button"
                  />
                ))}
              </div>
            </div>
            <PhonePreview
              currentCase={currentCase}
              frameLabel={frameLabel}
              mode={mode}
              state={state}
            />
          </div>

          <aside className={styles.inspector}>
            <section className={styles.inspectorSection}>
              <h2>
                <ClipboardList size={16} />
                验收断言
              </h2>
              <div className={styles.assertionGrid}>
                <div>
                  <span>Blocks</span>
                  <strong>{currentCase.expectations.blockTypes.join(", ") || "none"}</strong>
                </div>
                <div>
                  <span>Visible</span>
                  <strong>{currentCase.expectations.visibleBlockTypes.join(", ") || "none"}</strong>
                </div>
                <div>
                  <span>MCQ</span>
                  <strong>{currentCase.expectations.mcqCount}</strong>
                </div>
              </div>
            </section>

            <section className={styles.inspectorSection}>
              <h2>
                {currentCase.parityWarnings.length ? (
                  <AlertTriangle size={16} />
                ) : (
                  <CheckCircle2 size={16} />
                )}
                Final / History Parity
              </h2>
              <div
                className={styles.parityStatus}
                data-ok={currentCase.parityWarnings.length ? "false" : "true"}
                data-testid="harness-parity-status"
              >
                {currentCase.parityWarnings.length
                  ? currentCase.parityWarnings.join("; ")
                  : "实时最终态与历史恢复态一致"}
              </div>
            </section>

            <section className={styles.inspectorSection}>
              <h2>人工关注点</h2>
              {currentCase.manualFocus.length ? (
                <ul className={styles.tightList}>
                  {currentCase.manualFocus.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className={styles.muted}>该 case 暂无额外人工关注点。</p>
              )}
            </section>

            <section className={styles.inspectorSection}>
              <h2>当前 render model</h2>
              <pre className={styles.jsonBlock}>
                {JSON.stringify(
                  {
                    mode,
                    frame: mode === "stream" ? frameLabel : mode,
                    blockTypes: (state.blocks || []).map((block) => block.type),
                    visibleBlockTypes: (state.visibleBlocks || []).map((block) => block.type),
                    mcqCount: state.mcqCards?.length || 0,
                    hasStructuredContent: state.hasStructuredContent,
                    streamPhase: state.streamPhase,
                  },
                  null,
                  2,
                )}
              </pre>
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
