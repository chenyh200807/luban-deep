/* eslint-disable i18n/no-literal-ui-text -- Chinese-only invite campaign page. */
"use client";

import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Home,
  MessageSquareText,
  PenLine,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";

<<<<<<< Updated upstream
=======
type FormState = {
  name: string;
  phone: string;
  email: string;
  examType: string;
  examStage: string;
  painPoint: string;
  weeklyTime: string;
  wechatId: string;
  isYousenMember: string;
  examDate: string;
  currentMethod: string;
  latestWrongQuestion: string;
  acceptInterview: boolean;
  consent: boolean;
};

type FormErrors = Partial<Record<keyof FormState, string>>;

const initialForm: FormState = {
  name: "",
  phone: "",
  email: "",
  examType: "",
  examStage: "",
  painPoint: "",
  weeklyTime: "",
  wechatId: "",
  isYousenMember: "",
  examDate: "",
  currentMethod: "",
  latestWrongQuestion: "",
  acceptInterview: false,
  consent: false,
};

const examTypeOptions = ["一建建筑实务", "二建建筑实务", "一建/二建都在准备", "其他建工类考试"];
const stageOptions = ["刚开始学建筑实务", "已经学完一轮", "正在冲刺刷题", "案例题长期失分", "准备重新激活学习"];
const painOptions = ["案例题不会写", "错题原因不清楚", "知识点记不住", "听课懂了但做题不会", "缺少复习计划", "想知道自己薄弱章节"];
const weeklyTimeOptions = ["10 分钟以内", "10-30 分钟", "30-60 分钟", "1 小时以上"];
const examDateOptions = ["2026 年考试", "2027 年考试", "还没确定", "只想先体验"];
const yousenMemberOptions = ["佑森在读/已购学员", "曾经听过佑森课程", "非佑森学员", "不确定"];
>>>>>>> Stashed changes
const applyHref = "/invite-test/apply?utm_source=invite_test&utm_campaign=landing_page";

const featureItems = [
  {
    icon: FileText,
    title: "案例题 AI 阅卷官",
    text: "把作答拆成得分点、缺口和改写建议，优先验证建筑实务最痛的主观题场景。",
  },
  {
    icon: Target,
    title: "错因驱动陪练",
    text: "不是平均刷题，而是围绕质量验收、责任主体、流程依据等失分形状继续训练。",
  },
  {
    icon: BarChart3,
    title: "市场反应可量化",
    text: "用入口点击、申请、试用完成和回访意愿判断真实需求，而不是只看问卷好评。",
  },
];

const visionItems = [
  "让建筑实务学员不再只靠听课和刷题硬扛。",
  "把佑森课程、老师经验、题库证据和学员错因连接起来。",
  "用真实会员行为决定下一批产品开发方向。",
];

const audienceItems = [
  "正在学习一建/二建建筑实务",
  "案例题长期不知道怎么拿分",
  "听课能懂，但做题表达总不完整",
  "愿意用 10 分钟反馈真实体验",
];

const taskItems = [
  "完成 1 次建筑实务 AI 答疑",
  "提交 1 道案例题或错题诊断",
  "完成 3 分钟内测调研",
  "可选参与 10 分钟回访",
];

const signalItems = [
  ["点击", "是否对建筑实务 AI 有第一反应"],
  ["申请", "是否愿意留下身份进入测试"],
  ["试用", "是否真的完成案例题诊断"],
  ["回访", "是否愿意说出哪里有用和哪里无用"],
];

<<<<<<< Updated upstream
=======
function trackInviteEvent(name: string, detail?: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("luban-invite-event", { detail: { name, ...detail } }));
}

function validate(form: FormState): FormErrors {
  const errors: FormErrors = {};
  const phone = form.phone.replace(/\s+/g, "");
  const email = form.email.trim().toLowerCase();

  if (!form.name.trim()) errors.name = "请输入称呼，方便通过后联系你。";
  if (!/^1\d{10}$/.test(phone)) errors.phone = "请输入 11 位中国大陆手机号。";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = "请输入有效邮箱，方便接收内测通知。";
  if (!form.examType) errors.examType = "请选择你正在准备的考试。";
  if (!form.examStage) errors.examStage = "请选择你当前的备考阶段。";
  if (!form.painPoint) errors.painPoint = "请选择一个最想先解决的问题。";
  if (!form.weeklyTime) errors.weeklyTime = "请选择每周可参与测试的时间。";
  if (!form.consent) errors.consent = "请确认同意我们用于内测筛选与产品改进。";

  return errors;
}

type InviteApplicationFormProps = {
  sourcePage?: string;
};

export function InviteApplicationForm({ sourcePage = "invite-test-apply" }: InviteApplicationFormProps) {
  const [form, setForm] = useState<FormState>(initialForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const firstErrorRef = useRef<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | null>(null);
  const hasStartedRef = useRef(false);

  useEffect(() => {
    trackInviteEvent("invite_view", { source_page: sourcePage });
  }, [sourcePage]);

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    if (!hasStartedRef.current) {
      hasStartedRef.current = true;
      trackInviteEvent("invite_form_start", { first_field: key });
    }
    setForm((current) => ({ ...current, [key]: value }));
    setSubmitError("");
    setErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const setErrorRef = (
    key: keyof FormState,
    node: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | null,
  ) => {
    if (!node || firstErrorRef.current || !errors[key]) return;
    firstErrorRef.current = node;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    firstErrorRef.current = null;
    const nextErrors = validate(form);
    setErrors(nextErrors);

    if (Object.keys(nextErrors).length > 0) {
      trackInviteEvent("invite_submit_error", { reason: "validation" });
      requestAnimationFrame(() => firstErrorRef.current?.focus());
      return;
    }

    setIsSubmitting(true);
    setSubmitError("");

    try {
      const params = new URLSearchParams(window.location.search);
      const response = await fetch("/api/invite-test/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          phone: form.phone.replace(/\s+/g, ""),
          email: form.email.trim().toLowerCase(),
          sourcePage,
          utmSource: params.get("utm_source") || "",
          utmCampaign: params.get("utm_campaign") || "",
        }),
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok || !payload?.ok) {
        throw new Error(payload?.error || "申请提交失败，请稍后再试。");
      }

      trackInviteEvent("invite_submit_success", { application_id: payload.applicationId });
      setIsSubmitting(false);
      setSubmitted(true);
    } catch (error) {
      setIsSubmitting(false);
      setSubmitError(error instanceof Error ? error.message : "申请提交失败，请稍后再试。");
      trackInviteEvent("invite_submit_error", { reason: "network_or_server" });
    }
  };

  if (submitted) {
    return (
      <div className="flex min-h-[560px] flex-col items-start justify-center rounded-[1.75rem] border border-white/10 bg-[#111927]/[0.92] p-8 shadow-[0_28px_90px_rgba(0,0,0,0.42)]">
        <div className="rounded-full bg-[#103e66] p-4">
          <CheckCircle2 className="h-10 w-10 text-[#7ac5ff]" aria-hidden="true" />
        </div>
        <h2 className="mt-8 text-4xl font-black tracking-normal text-white">申请已提交，等待筛选</h2>
        <p className="mt-4 max-w-xl text-base leading-7 text-white/[0.62]" aria-live="polite">
          如果你进入首批内测，我们会联系你完成一次真实错题体验。你可以先准备一道最近做错的建筑实务选择题或案例题答案。
        </p>
        <button
          type="button"
          onClick={() => {
            setSubmitted(false);
            setForm(initialForm);
          }}
          className="mt-8 rounded-full border border-white/[0.16] bg-white/[0.06] px-5 py-3 text-sm font-bold text-white/[0.78] transition-colors duration-200 hover:bg-white/[0.10] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]"
        >
          继续提交另一位学员
        </button>
      </div>
    );
  }

  return (
    <form
      className="space-y-6 rounded-[1.75rem] border border-white/10 bg-[#111927]/[0.92] p-5 shadow-[0_28px_90px_rgba(0,0,0,0.42)] sm:p-7"
      noValidate
      onSubmit={handleSubmit}
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="name" className="block text-sm font-bold text-white/[0.86]">
            姓名或称呼
          </label>
          <input
            ref={(node) => setErrorRef("name", node)}
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            value={form.name}
            onChange={(event) => updateForm("name", event.target.value)}
            placeholder="例如：张同学…"
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "name-error" : undefined}
          />
          {errors.name ? <p id="name-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.name}</p> : null}
        </div>

        <div>
          <label htmlFor="phone" className="block text-sm font-bold text-white/[0.86]">
            手机号（必填）
          </label>
          <input
            ref={(node) => setErrorRef("phone", node)}
            id="phone"
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            required
            aria-required="true"
            value={form.phone}
            onChange={(event) => updateForm("phone", event.target.value)}
            placeholder="例如：13800138000…"
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            aria-invalid={Boolean(errors.phone)}
            aria-describedby={errors.phone ? "phone-error" : undefined}
          />
          {errors.phone ? <p id="phone-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.phone}</p> : null}
        </div>
      </div>

      <div>
        <label htmlFor="email" className="block text-sm font-bold text-white/[0.86]">
          邮箱（必填）
        </label>
        <input
          ref={(node) => setErrorRef("email", node)}
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          aria-required="true"
          value={form.email}
          onChange={(event) => updateForm("email", event.target.value)}
          placeholder="例如：name@example.com"
          className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? "email-error" : undefined}
        />
        {errors.email ? <p id="email-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.email}</p> : null}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="exam-type" className="block text-sm font-bold text-white/[0.86]">
            正在准备的考试
          </label>
          <select
            ref={(node) => setErrorRef("examType", node)}
            id="exam-type"
            name="examType"
            autoComplete="off"
            value={form.examType}
            onChange={(event) => updateForm("examType", event.target.value)}
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            aria-invalid={Boolean(errors.examType)}
            aria-describedby={errors.examType ? "exam-type-error" : undefined}
          >
            <option value="">请选择考试</option>
            {examTypeOptions.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          {errors.examType ? <p id="exam-type-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.examType}</p> : null}
        </div>

        <div>
          <label htmlFor="exam-date" className="block text-sm font-bold text-white/[0.86]">
            预计考试时间
          </label>
          <select
            id="exam-date"
            name="examDate"
            autoComplete="off"
            value={form.examDate}
            onChange={(event) => updateForm("examDate", event.target.value)}
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          >
            <option value="">可选</option>
            {examDateOptions.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="exam-stage" className="block text-sm font-bold text-white/[0.86]">
          当前备考阶段
        </label>
        <select
          ref={(node) => setErrorRef("examStage", node)}
          id="exam-stage"
          name="examStage"
          autoComplete="off"
          value={form.examStage}
          onChange={(event) => updateForm("examStage", event.target.value)}
          className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          aria-invalid={Boolean(errors.examStage)}
          aria-describedby={errors.examStage ? "exam-stage-error" : undefined}
        >
          <option value="">请选择阶段</option>
          {stageOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        {errors.examStage ? <p id="exam-stage-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.examStage}</p> : null}
      </div>

      <fieldset>
        <legend className="text-sm font-bold text-white/[0.86]">最想先解决的问题</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {painOptions.map((option) => (
            <label
              key={option}
              className="flex min-h-14 cursor-pointer items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm font-semibold text-white/[0.72] transition-colors duration-200 hover:border-white/[0.24] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[#5bbcff]"
            >
              <input
                ref={(node) => {
                  if (option === painOptions[0]) setErrorRef("painPoint", node);
                }}
                type="radio"
                name="painPoint"
                value={option}
                checked={form.painPoint === option}
                onChange={(event) => updateForm("painPoint", event.target.value)}
                className="h-4 w-4 accent-[#5bbcff]"
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
        {errors.painPoint ? <p className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.painPoint}</p> : null}
      </fieldset>

      <div>
        <label htmlFor="weekly-time" className="block text-sm font-bold text-white/[0.86]">
          每周可参与测试时间
        </label>
        <select
          ref={(node) => setErrorRef("weeklyTime", node)}
          id="weekly-time"
          name="weeklyTime"
          autoComplete="off"
          value={form.weeklyTime}
          onChange={(event) => updateForm("weeklyTime", event.target.value)}
          className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          aria-invalid={Boolean(errors.weeklyTime)}
          aria-describedby={errors.weeklyTime ? "weekly-time-error" : undefined}
        >
          <option value="">请选择时间</option>
          {weeklyTimeOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        {errors.weeklyTime ? <p id="weekly-time-error" className="mt-2 text-sm leading-6 text-[#ff9c7a]">{errors.weeklyTime}</p> : null}
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="wechat-id" className="block text-sm font-bold text-white/[0.86]">
            微信号（选填）
          </label>
          <input
            id="wechat-id"
            name="wechatId"
            type="text"
            autoComplete="off"
            value={form.wechatId}
            onChange={(event) => updateForm("wechatId", event.target.value)}
            placeholder="方便通过后拉你进内测"
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          />
        </div>

        <div>
          <label htmlFor="yousen-member" className="block text-sm font-bold text-white/[0.86]">
            是否佑森学员（选填）
          </label>
          <select
            id="yousen-member"
            name="isYousenMember"
            autoComplete="off"
            value={form.isYousenMember}
            onChange={(event) => updateForm("isYousenMember", event.target.value)}
            className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
          >
            <option value="">可选</option>
            {yousenMemberOptions.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="current-method" className="block text-sm font-bold text-white/[0.86]">
          你现在通常怎么解决这个问题
        </label>
        <textarea
          id="current-method"
          name="currentMethod"
          autoComplete="off"
          value={form.currentMethod}
          onChange={(event) => updateForm("currentMethod", event.target.value)}
          placeholder="例如：问老师、刷题、看解析、用通用 AI、暂时跳过…"
          rows={4}
          className="mt-2 w-full resize-y rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base leading-7 text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
        />
      </div>

      <div>
        <label htmlFor="latest-wrong-question" className="block text-sm font-bold text-white/[0.86]">
          最近一道错题或案例题答案（选填）
        </label>
        <textarea
          id="latest-wrong-question"
          name="latestWrongQuestion"
          autoComplete="off"
          value={form.latestWrongQuestion}
          onChange={(event) => updateForm("latestWrongQuestion", event.target.value)}
          placeholder="可以粘贴题干、你的答案，或简单描述你最近卡住的题。"
          rows={5}
          className="mt-2 w-full resize-y rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base leading-7 text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
        />
      </div>

      <div className="space-y-3">
        <label className="flex cursor-pointer gap-3 rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-sm leading-6 text-white/[0.66] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[#5bbcff]">
          <input
            type="checkbox"
            name="acceptInterview"
            checked={form.acceptInterview}
            onChange={(event) => updateForm("acceptInterview", event.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 accent-[#5bbcff]"
          />
          <span>我愿意在通过后接受一次 10 分钟回访，帮助团队判断真实需求。</span>
        </label>
        <label className="flex cursor-pointer gap-3 rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-sm leading-6 text-white/[0.66] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[#5bbcff]">
          <input
            ref={(node) => setErrorRef("consent", node)}
            type="checkbox"
            name="consent"
            checked={form.consent}
            onChange={(event) => updateForm("consent", event.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 accent-[#5bbcff]"
            aria-invalid={Boolean(errors.consent)}
            aria-describedby={errors.consent ? "consent-error" : undefined}
          />
          <span>我同意将申请信息和内测反馈用于筛选、产品改进和用户需求分析。</span>
        </label>
        {errors.consent ? <p id="consent-error" className="text-sm leading-6 text-[#ff9c7a]">{errors.consent}</p> : null}
      </div>

      <div aria-live="polite" className="min-h-6 text-sm text-white/[0.52]">
        {submitError || (isSubmitting ? "正在提交申请…" : "提交后不会自动获得名额，我们会按批次筛选并联系。")}
      </div>

      <button
        type="submit"
        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#2f8fff] px-6 py-4 text-base font-black text-white shadow-[0_0_42px_rgba(47,143,255,0.38)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] disabled:cursor-wait disabled:bg-[#3b6388]"
        disabled={isSubmitting}
      >
        {isSubmitting ? "提交中…" : "提交内测申请"}
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </form>
  );
}

>>>>>>> Stashed changes
export default function InviteTestPage() {
  return (
    <div
      lang="zh-CN"
      className="h-screen touch-manipulation overflow-y-auto overflow-x-hidden bg-[#080c18] text-white selection:bg-[#5bbcff] selection:text-[#04111d]"
    >
      <a
        href="#highlights"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[#08111f]"
      >
        跳到产品亮点
      </a>

      <header className="fixed left-0 right-0 top-0 z-40 border-b border-white/[0.08] bg-[#080c18]/[0.78] backdrop-blur-xl">
        <nav
          aria-label="鲁班智考内测导航"
          className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8"
        >
          <Link
            href="/intro"
            aria-label="返回鲁班智考首页"
            className="flex min-w-0 items-center gap-3 rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]"
          >
            <Image
              src="/images/logo-white.png"
              alt="鲁班智考"
              width={135}
              height={151}
              priority
              style={{ width: "auto", height: 36 }}
            />
          </Link>
          <div className="hidden items-center gap-8 text-sm font-semibold text-white/[0.62] md:flex">
            <a href="#highlights" className="rounded-md hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]">
              产品亮点
            </a>
            <a href="#signals" className="rounded-md hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]">
              市场信号
            </a>
            <Link href={applyHref} className="rounded-md hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]">
              申请
            </Link>
            <Link href="/intro" className="inline-flex items-center gap-1 rounded-md hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]">
              <Home className="h-4 w-4" aria-hidden="true" />
              首页
            </Link>
          </div>
<<<<<<< Updated upstream
          <Link
            href={applyHref}
            className="inline-flex items-center gap-2 rounded-full bg-[#2f8fff] px-4 py-2 text-sm font-semibold text-white shadow-[0_0_34px_rgba(47,143,255,0.34)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]"
          >
            申请内测
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
=======
          <div className="flex items-center gap-2">
            <Link
              href="/intro"
              className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.14] bg-white/[0.06] px-3 py-2 text-xs font-bold text-white/[0.76] transition-colors duration-200 hover:border-white/[0.26] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:px-4 sm:text-sm"
            >
              <Home className="h-4 w-4" aria-hidden="true" />
              <span className="sm:hidden">首页</span>
              <span className="hidden sm:inline">返回首页</span>
            </Link>
            <Link
              href={applyHref}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#2f8fff] px-3 py-2 text-xs font-semibold text-white shadow-[0_0_34px_rgba(47,143,255,0.34)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:px-4 sm:text-sm"
            >
              申请内测
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
>>>>>>> Stashed changes
        </nav>
      </header>

      <main>
        <section className="relative min-h-[920px] overflow-hidden pt-16 sm:min-h-[960px] lg:min-h-[900px]">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,#080c18_0%,#0e1828_48%,#080c18_100%)]" />
          <Image
            src="/images/bg_horizon.jpg"
            alt=""
            fill
            priority
            sizes="100vw"
            className="pointer-events-none absolute inset-0 object-cover object-bottom opacity-90"
          />
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(8,12,24,0.68)_0%,rgba(8,12,24,0.12)_45%,rgba(8,12,24,0.9)_100%)]" />
          <div className="pointer-events-none absolute inset-x-0 top-20 h-[34rem] bg-[radial-gradient(ellipse_at_center,rgba(47,143,255,0.23)_0%,rgba(47,143,255,0.1)_34%,transparent_70%)]" />

          <div className="relative z-10 mx-auto flex max-w-7xl flex-col items-center px-5 pb-20 pt-16 text-center sm:px-8 sm:pt-20">
            <div className="inline-flex items-center gap-3 rounded-full border border-white/[0.18] bg-white/[0.08] px-4 py-2 text-sm font-semibold text-white/[0.86] shadow-[inset_0_1px_0_rgba(255,255,255,0.18)] backdrop-blur-md">
              <Sparkles className="h-4 w-4 text-[#75bdff]" aria-hidden="true" />
              佑森建筑实务会员内测招募
            </div>

            <h1 className="mt-20 max-w-6xl text-balance text-[3.2rem] font-black leading-[1.02] tracking-normal text-white sm:mt-24 sm:text-7xl lg:text-[6rem]">
              鲁班智考 AI
              <span className="block text-[#66b6ff]">建筑实务内测申请</span>
            </h1>
            <p className="mt-6 max-w-3xl text-pretty text-lg font-semibold leading-8 text-white/[0.64] drop-shadow-[0_2px_14px_rgba(0,0,0,0.88)] sm:text-xl">
              用申请制内测验证真实需求：学员是否愿意提交错题、完成体验，并告诉我们哪里值得继续开发。
            </p>

            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href={applyHref}
                className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#2f8fff] px-7 py-4 text-base font-black text-white shadow-[0_0_42px_rgba(47,143,255,0.42)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:w-auto"
              >
                申请内测
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <a
                href="#signals"
                className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-white/[0.14] bg-black/[0.18] px-7 py-4 text-base font-bold text-white/[0.76] transition-colors duration-200 hover:border-white/[0.28] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:w-auto"
              >
                看市场信号
                <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>

            <div className="mx-auto mt-10 w-full max-w-5xl rounded-[1.75rem] border border-white/[0.14] bg-[#121927]/[0.78] p-4 text-left shadow-[0_28px_100px_rgba(0,0,0,0.48)] backdrop-blur-md">
              <div className="rounded-[1.25rem] border border-white/[0.10] bg-[#0c1320]/[0.92] p-5 sm:p-6">
                <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
                  <div>
                    <p className="text-sm font-black tracking-[0.22em] text-[#66b6ff]">INVITE TEST</p>
                    <h2 className="mt-4 max-w-2xl text-2xl font-black leading-tight tracking-normal text-white sm:text-3xl">
                      先让学员主动申请，再把申请内容沉淀成调研报告
                    </h2>
                    <p className="mt-3 max-w-2xl text-sm leading-7 text-white/[0.58]">
                      这不是公开报名页，而是用佑森已有建筑实务用户池做小批量需求验证。
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-4">
                      <p className="text-xs font-bold text-white/[0.48]">验证目标</p>
                      <p className="mt-2 text-sm font-bold text-white">市场兴趣 + 真实痛点</p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-4">
                      <p className="text-xs font-bold text-white/[0.48]">首批规则</p>
                      <p className="mt-2 text-sm font-bold text-white">申请制，不按先到先得</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="highlights" className="scroll-mt-24 bg-[#080c18] px-5 py-20 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
              <div>
                <p className="text-sm font-black tracking-[0.22em] text-[#66b6ff]">PRODUCT HIGHLIGHTS</p>
                <h2 className="mt-5 max-w-3xl text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                  不是泛 AI 工具，是建筑实务学习场景
                </h2>
              </div>
              <p className="max-w-2xl text-pretty text-base leading-7 text-white/[0.58] lg:justify-self-end">
                首批页面只讲最强钩子：案例题批改、错因陪练、真实市场反馈。申请表承接调研信息，减少后续产品方向的盲猜。
              </p>
            </div>

            <div className="mt-10 grid gap-4 lg:grid-cols-3">
              {featureItems.map((item) => {
                const Icon = item.icon;
                return (
                  <article
                    key={item.title}
                    className="rounded-[1.4rem] border border-white/10 bg-[#111927]/[0.70] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                  >
                    <div className="grid h-12 w-12 place-items-center rounded-2xl border border-white/[0.10] bg-white/[0.06]">
                      <Icon className="h-6 w-6 text-[#66b6ff]" aria-hidden="true" />
                    </div>
                    <h3 className="mt-7 text-2xl font-black tracking-normal text-white">{item.title}</h3>
                    <p className="mt-4 text-sm leading-7 text-white/[0.58]">{item.text}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="border-y border-white/10 bg-[#0c1320] px-5 py-20 sm:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <ShieldCheck className="h-7 w-7 text-[#66b6ff]" aria-hidden="true" />
              <h2 className="mt-6 text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                愿景是把学习反馈变成下一步行动
              </h2>
            </div>
            <div className="grid gap-4">
              {visionItems.map((item) => (
                <div key={item} className="flex gap-4 rounded-[1.4rem] border border-white/10 bg-white/[0.045] p-5">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-[#83d4ff]" aria-hidden="true" />
                  <p className="text-base font-semibold leading-7 text-white/[0.78]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-[#080c18] px-5 py-20 sm:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <h2 className="text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                更适合首批邀请的学员
              </h2>
              <p className="mt-5 max-w-xl text-base leading-7 text-white/[0.58]">
                我们更看重反馈质量，不按先到先得。越能描述真实学习卡点，越适合进入首批。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {audienceItems.map((item) => (
                <div key={item} className="flex gap-3 rounded-[1.2rem] border border-white/10 bg-white/[0.045] p-4">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-[#83d4ff]" aria-hidden="true" />
                  <p className="text-sm font-semibold leading-6 text-white/[0.72]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-y border-white/10 bg-[#0c1320] px-5 py-20 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="max-w-3xl">
              <p className="text-sm font-black tracking-[0.22em] text-[#66b6ff]">AFTER APPROVAL</p>
              <h2 className="mt-5 text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                通过后要完成的测试任务
              </h2>
            </div>
            <div className="mt-10 grid gap-4 md:grid-cols-4">
              {taskItems.map((item, index) => (
                <div key={item} className="rounded-[1.3rem] border border-white/10 bg-[#101928]/[0.72] p-5">
                  <p className="font-mono text-sm font-black tracking-[0.16em] text-[#66b6ff]">
                    {String(index + 1).padStart(2, "0")}
                  </p>
                  <p className="mt-6 text-sm font-semibold leading-6 text-white/[0.72]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="signals" className="scroll-mt-24 bg-[#080c18] px-5 py-20 sm:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-start">
            <div>
              <div className="inline-flex items-center gap-3 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-bold text-white/[0.72]">
                <ClipboardCheck className="h-4 w-4 text-[#66b6ff]" aria-hidden="true" />
                市场兴趣验证
              </div>
              <h2 className="mt-6 text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                我们真正要看的，是市场行为
              </h2>
              <p className="mt-5 text-pretty text-base leading-7 text-white/[0.60]">
                这次不是做一个漂亮问卷，而是用佑森已有建筑实务学员池做小批量验证，判断用户是否真的愿意进入、试用、反馈和留下。
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {signalItems.map(([label, text], index) => (
                <article key={label} className="rounded-[1.25rem] border border-white/10 bg-[#101928]/[0.72] p-5">
                  <p className="font-mono text-sm font-black tracking-[0.16em] text-[#66b6ff]">
                    {String(index + 1).padStart(2, "0")}
                  </p>
                  <h3 className="mt-6 text-2xl font-black text-white">{label}</h3>
                  <p className="mt-3 text-sm leading-6 text-white/[0.56]">{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="apply" className="scroll-mt-24 bg-[#0c1320] px-5 py-20 sm:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.74fr_1.26fr] lg:items-start">
            <div className="lg:sticky lg:top-24">
              <div className="inline-flex items-center gap-3 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-bold text-white/[0.72]">
                <PenLine className="h-4 w-4 text-[#66b6ff]" aria-hidden="true" />
                内测申请
              </div>
              <h2 className="mt-6 text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-5xl">
                提交申请，进入首批测试池
              </h2>
              <p className="mt-5 text-pretty text-base leading-7 text-white/[0.60]">
                表单会帮助我们判断学习阶段、真实痛点、可测试时间和是否适合回访。提交后不会自动获得名额，我们会按批次筛选。
              </p>
              <div className="mt-8 rounded-[1.35rem] border border-white/10 bg-white/[0.045] p-5">
                <MessageSquareText className="h-6 w-6 text-[#66b6ff]" aria-hidden="true" />
                <p className="mt-4 text-sm leading-7 text-white/[0.58]">
                  申请信息会在单独页面收集，包含手机、邮箱、备考阶段、真实痛点和可参与测试时间，便于后续筛选与回访。
                </p>
              </div>
            </div>
            <div className="rounded-[1.75rem] border border-white/10 bg-[#111927]/[0.92] p-6 shadow-[0_28px_90px_rgba(0,0,0,0.42)] sm:p-8">
<<<<<<< Updated upstream
              <p className="text-sm font-black tracking-[0.20em] text-[#66b6ff]">APPLICATION WINDOW</p>
              <h3 className="mt-5 text-3xl font-black tracking-normal text-white sm:text-4xl">
                填写内测申请表
              </h3>
              <p className="mt-4 max-w-2xl text-base leading-8 text-white/[0.60]">
                我们把申请表独立出来，避免在介绍页里打断阅读。提交后信息会进入内测筛选池，通过后再进入微信小程序体验。
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/[0.055] p-4">
                  <p className="text-sm font-black text-white">邮箱和手机必填</p>
                  <p className="mt-2 text-sm leading-6 text-white/[0.54]">用于发送内测通知、体验说明和后续回访安排。</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.055] p-4">
                  <p className="text-sm font-black text-white">通过后进小程序</p>
                  <p className="mt-2 text-sm leading-6 text-white/[0.54]">真实体验以微信小程序里的陪考对话和案例题批改为主。</p>
                </div>
              </div>
              <Link
                href={applyHref}
                className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#2f8fff] px-7 py-4 text-base font-black text-white shadow-[0_0_42px_rgba(47,143,255,0.38)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:w-auto"
              >
                申请内测体验
=======
              <p className="text-sm font-black tracking-[0.2em] text-[#66b6ff]">APPLICATION PAGE</p>
              <h3 className="mt-5 text-3xl font-black leading-tight tracking-normal text-white sm:text-4xl">
                申请信息单独收集，方便后续筛选和联系
              </h3>
              <p className="mt-4 text-base leading-7 text-white/[0.62]">
                申请页会收集称呼、手机号、邮箱、备考阶段、核心痛点和可测试时间。通过后我们会按批次联系你完成小程序真实错题体验。
              </p>
              <div className="mt-7 grid gap-3 sm:grid-cols-3">
                {["必填邮箱", "申请制筛选", "小程序体验"].map((item) => (
                  <div key={item} className="rounded-2xl border border-white/10 bg-white/[0.055] px-4 py-3 text-sm font-bold text-white/[0.76]">
                    {item}
                  </div>
                ))}
              </div>
              <Link
                href={applyHref}
                className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#2f8fff] px-6 py-4 text-base font-black text-white shadow-[0_0_42px_rgba(47,143,255,0.38)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:w-auto"
              >
                前往申请页
>>>>>>> Stashed changes
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
