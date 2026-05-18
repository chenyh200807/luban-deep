/* eslint-disable i18n/no-literal-ui-text -- Chinese-only invite application form. */
"use client";

import { ArrowRight, CheckCircle2 } from "lucide-react";
import { FormEvent, useRef, useState } from "react";

type FormState = {
  name: string;
  phone: string;
  email: string;
  province: string;
  ageRange: string;
  education: string;
  occupation: string;
  examType: string;
  examStage: string;
  preparationYears: string;
  knowledgeFoundation: string;
  painPoint: string;
  weeklyTime: string;
  dailyStudyTime: string;
  currentMethod: string;
  studyDifficulties: string;
  wechatId: string;
  isYousenMember: string;
  examDate: string;
  latestWrongQuestion: string;
  acceptInterview: boolean;
  consent: boolean;
};

type FormErrors = Partial<Record<keyof FormState | "submit", string>>;

const initialForm: FormState = {
  name: "",
  phone: "",
  email: "",
  province: "",
  ageRange: "",
  education: "",
  occupation: "",
  examType: "",
  examStage: "",
  preparationYears: "",
  knowledgeFoundation: "",
  painPoint: "",
  weeklyTime: "",
  dailyStudyTime: "",
  currentMethod: "",
  studyDifficulties: "",
  wechatId: "",
  isYousenMember: "",
  examDate: "",
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
const ageRangeOptions = ["18-25 岁", "26-35 岁", "36-45 岁", "45 岁以上"];
const preparationYearsOptions = ["首次备考", "第 2 次备考", "第 3 次备考", "3 次以上备考"];
const knowledgeFoundationOptions = ["0 基础", "基础薄弱", "一般", "扎实"];
const dailyStudyTimeOptions = ["30 分钟以内", "30-60 分钟", "1-2 小时", "2 小时以上", "不固定"];

function validate(form: FormState): FormErrors {
  const errors: FormErrors = {};
  const phone = form.phone.replace(/\s+/g, "");
  const email = form.email.trim();

  if (!form.name.trim()) errors.name = "请输入称呼，方便通过后联系你。";
  if (!/^1\d{10}$/.test(phone)) errors.phone = "请输入 11 位中国大陆手机号。";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = "请输入有效邮箱，用于接收内测通知。";
  if (!form.examType) errors.examType = "请选择正在准备的考试。";
  if (!form.examStage) errors.examStage = "请选择你当前的备考阶段。";
  if (!form.painPoint) errors.painPoint = "请选择一个最想先解决的问题。";
  if (!form.weeklyTime) errors.weeklyTime = "请选择每周可参与测试的时间。";
  if (!form.consent) errors.consent = "请确认同意我们用于内测筛选与产品改进。";

  return errors;
}

function getCampaignParams() {
  if (typeof window === "undefined") {
    return { utmSource: "", utmCampaign: "" };
  }
  const params = new URLSearchParams(window.location.search);
  return {
    utmSource: params.get("utm_source") ?? "",
    utmCampaign: params.get("utm_campaign") ?? "",
  };
}

export function InviteApplicationForm({ sourcePage }: { sourcePage: string }) {
  const [form, setForm] = useState<FormState>(initialForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const firstErrorRef = useRef<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | null>(null);

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      if (!current[key] && !current.submit) return current;
      const next = { ...current };
      delete next[key];
      delete next.submit;
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
      requestAnimationFrame(() => firstErrorRef.current?.focus());
      return;
    }

    const { utmSource, utmCampaign } = getCampaignParams();
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/invite-test/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          phone: form.phone.replace(/\s+/g, ""),
          email: form.email.trim().toLowerCase(),
          sourcePage,
          utmSource,
          utmCampaign,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.error === "string" ? payload.error : "提交失败，请稍后再试。");
      }

      setSubmitted(true);
    } catch (error) {
      setErrors((current) => ({
        ...current,
        submit: error instanceof Error ? error.message : "提交失败，请稍后再试。",
      }));
    } finally {
      setIsSubmitting(false);
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
          我们会按首批名额和学习画像筛选。通过后将通过手机或邮箱联系你进入小程序内测任务，并优先邀请完成度高的学员参与回访。
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
            placeholder="例如：张同学..."
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
            placeholder="例如：13800138000..."
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

      <section className="space-y-5 rounded-3xl border border-white/10 bg-white/[0.035] p-4 sm:p-5">
        <div>
          <p className="text-sm font-black text-white/[0.88]">基础画像</p>
          <p className="mt-1 text-xs leading-5 text-white/[0.48]">用于判断首批内测匹配度，不会作为公开注册承诺。</p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="province" className="block text-sm font-bold text-white/[0.86]">
              所在省份
            </label>
            <input
              id="province"
              name="province"
              type="text"
              autoComplete="address-level1"
              value={form.province}
              onChange={(event) => updateForm("province", event.target.value)}
              placeholder="例如：江苏、广东、山东..."
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            />
          </div>

          <div>
            <label htmlFor="education" className="block text-sm font-bold text-white/[0.86]">
              学历
            </label>
            <input
              id="education"
              name="education"
              type="text"
              autoComplete="off"
              value={form.education}
              onChange={(event) => updateForm("education", event.target.value)}
              placeholder="例如：大专、本科、研究生..."
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            />
          </div>
        </div>

        <fieldset>
          <legend className="text-sm font-bold text-white/[0.86]">年龄</legend>
          <div className="mt-3 grid gap-3 sm:grid-cols-4">
            {ageRangeOptions.map((option) => (
              <label
                key={option}
                className="flex min-h-12 cursor-pointer items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm font-semibold text-white/[0.72] transition-colors duration-200 hover:border-white/[0.24] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[#5bbcff]"
              >
                <input
                  type="radio"
                  name="ageRange"
                  value={option}
                  checked={form.ageRange === option}
                  onChange={(event) => updateForm("ageRange", event.target.value)}
                  className="h-4 w-4 accent-[#5bbcff]"
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="occupation" className="block text-sm font-bold text-white/[0.86]">
              当前职业
            </label>
            <input
              id="occupation"
              name="occupation"
              type="text"
              autoComplete="organization-title"
              value={form.occupation}
              onChange={(event) => updateForm("occupation", event.target.value)}
              placeholder="例如：施工员、项目经理、资料员..."
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            />
          </div>

          <div>
            <label htmlFor="preparation-years" className="block text-sm font-bold text-white/[0.86]">
              报考年限
            </label>
            <select
              id="preparation-years"
              name="preparationYears"
              autoComplete="off"
              value={form.preparationYears}
              onChange={(event) => updateForm("preparationYears", event.target.value)}
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            >
              <option value="">请选择第几次备考</option>
              {preparationYearsOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="knowledge-foundation" className="block text-sm font-bold text-white/[0.86]">
              专业知识基础
            </label>
            <select
              id="knowledge-foundation"
              name="knowledgeFoundation"
              autoComplete="off"
              value={form.knowledgeFoundation}
              onChange={(event) => updateForm("knowledgeFoundation", event.target.value)}
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            >
              <option value="">请选择基础情况</option>
              {knowledgeFoundationOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="daily-study-time" className="block text-sm font-bold text-white/[0.86]">
              每日固定学习时长
            </label>
            <select
              id="daily-study-time"
              name="dailyStudyTime"
              autoComplete="off"
              value={form.dailyStudyTime}
              onChange={(event) => updateForm("dailyStudyTime", event.target.value)}
              className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-[#172235] px-4 py-3 text-base text-white transition-colors duration-200 hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
            >
              <option value="">请选择每日学习时长</option>
              {dailyStudyTimeOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

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

      <div className="grid gap-5 sm:grid-cols-2">
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

        <div>
          <label htmlFor="is-yousen-member" className="block text-sm font-bold text-white/[0.86]">
            佑森学习关系
          </label>
          <select
            id="is-yousen-member"
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
          placeholder="例如：问老师、刷题、看解析、用通用 AI、暂时跳过..."
          rows={3}
          className="mt-2 w-full resize-y rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base leading-7 text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
        />
      </div>

      <div>
        <label htmlFor="study-difficulties" className="block text-sm font-bold text-white/[0.86]">
          备考学习存在的主要难点
        </label>
        <textarea
          id="study-difficulties"
          name="studyDifficulties"
          autoComplete="off"
          value={form.studyDifficulties}
          onChange={(event) => updateForm("studyDifficulties", event.target.value)}
          placeholder="例如：工作忙没时间、基础概念不牢、案例题不会组织语言、错题复盘坚持不下来..."
          rows={3}
          className="mt-2 w-full resize-y rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base leading-7 text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
        />
      </div>

      <div>
        <label htmlFor="latest-wrong-question" className="block text-sm font-bold text-white/[0.86]">
          最近一道错题或案例题描述
        </label>
        <textarea
          id="latest-wrong-question"
          name="latestWrongQuestion"
          autoComplete="off"
          value={form.latestWrongQuestion}
          onChange={(event) => updateForm("latestWrongQuestion", event.target.value)}
          placeholder="可提前准备一段案例题作答，进入小程序后更容易体验批改效果。"
          rows={4}
          className="mt-2 w-full resize-y rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base leading-7 text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
        />
      </div>

      <div>
        <label htmlFor="wechat-id" className="block text-sm font-bold text-white/[0.86]">
          微信号
        </label>
        <input
          id="wechat-id"
          name="wechatId"
          type="text"
          autoComplete="off"
          value={form.wechatId}
          onChange={(event) => updateForm("wechatId", event.target.value)}
          placeholder="可选，用于通过后更快沟通。"
          className="mt-2 w-full rounded-2xl border border-white/[0.12] bg-white/[0.07] px-4 py-3 text-base text-white transition-colors duration-200 placeholder:text-white/[0.32] hover:border-white/[0.24] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5bbcff]"
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
        {isSubmitting ? "正在提交申请..." : "提交后不会自动获得名额，我们会按批次筛选并联系。"}
      </div>
      {errors.submit ? (
        <p className="rounded-2xl border border-[#ff9c7a]/40 bg-[#321b16] px-4 py-3 text-sm leading-6 text-[#ffb79c]">
          {errors.submit}
        </p>
      ) : null}

      <button
        type="submit"
        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#2f8fff] px-6 py-4 text-base font-black text-white shadow-[0_0_42px_rgba(47,143,255,0.38)] transition-colors duration-200 hover:bg-[#58a8ff] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] disabled:cursor-wait disabled:bg-[#3b6388]"
        disabled={isSubmitting}
      >
        {isSubmitting ? "提交中..." : "提交内测申请"}
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </form>
  );
}
