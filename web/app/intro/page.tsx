/* eslint-disable i18n/no-literal-ui-text -- Chinese-only product landing page. */
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import styles from "./intro.module.css";
import {
  ArrowRight,
  BookOpenCheck,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  GraduationCap,
  Lightbulb,
  ListChecks,
  PenLine,
  RefreshCcw,
  Route,
  Sparkles,
  Target,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export const metadata: Metadata = {
  title: "鲁班智考 AI 实务教练",
  description: "鲁班智考是越用越懂你的专属个性化 AI 陪考教练，帮你批改作答、拆解采分点、诊断错因，并规划下一步训练。",
};

type IconItem = {
  icon: LucideIcon;
  title: string;
  text: string;
};

const navItems = [
  { label: "痛点", href: "#pain" },
  { label: "批改", href: "#grading" },
  { label: "教练", href: "#coach" },
  { label: "对比", href: "#compare" },
  { label: "Demo", href: "#demo" },
];

const painItems = [
  "看解析时觉得懂了，换一道题还是错。",
  "案例题写了一大段，不知道哪些话能得分。",
  "错题本越积越多，却不知道真正薄弱点是什么。",
  "老师讲课能听懂，自己答题却写不到采分点上。",
  "每天都在刷题，但没人告诉你下一步到底该练什么。",
];

const heroSignals = ["专属陪考", "采分点批改", "错因画像", "训练计划"];

const heroFlow = ["你的作答", "错因画像", "陪考记忆", "下一题"];

const coachSteps = [
  { icon: ClipboardCheck, title: "批改作答", text: "按采分点拆命中、漏点和表达问题。" },
  { icon: Target, title: "诊断错因", text: "区分概念混淆、审题失误、干扰项误导和关键词漏看。" },
  { icon: PenLine, title: "改写表达", text: "把口号式答案改成更像考试答案的短句和分点。" },
  { icon: Route, title: "陪你规划", text: "根据你的错因画像，把每次错题转化成下一步训练方向。" },
];

const featureItems: IconItem[] = [
  {
    icon: FileText,
    title: "案例题 AI 阅卷",
    text: "把你的案例题答案交给鲁班智考，它会按采分点拆解作答，指出命中点、漏分点和表达问题。",
  },
  {
    icon: ListChecks,
    title: "选择题错因诊断",
    text: "不只是告诉你正确答案，还会分析你为什么选错，哪个选项在干扰你，下次怎么判断。",
  },
  {
    icon: PenLine,
    title: "得分表达改写",
    text: "把“加强管理、做好检查”这类泛泛表达，改写成更容易拿分的程序性采分点表达。",
  },
  {
    icon: RefreshCcw,
    title: "错题复盘",
    text: "每一道错题都会沉淀成错因标签、薄弱考点和下一步训练建议，而不是只进入错题本。",
  },
  {
    icon: UserRound,
    title: "越用越懂你的陪考记忆",
    text: "持续记录你的常错考点、答题习惯、案例题表达问题和复盘轨迹，让后续讲解和推荐越来越像专属陪考专家。",
  },
  {
    icon: BookOpenCheck,
    title: "建筑实务专用知识库",
    text: "针对规范数字、程序边界、采分点和易错概念，优先结合题库、教材和检索证据回答。",
  },
];

const comparisonRows = [
  ["我想知道答案", "给标准答案和解析", "给答案，也解释你为什么会错"],
  ["我想知道案例题能得几分", "通常难以细批", "按采分点拆命中、漏点和表达"],
  ["我看懂解析但还会错", "继续刷更多题", "诊断错因，给迁移判断抓手"],
  ["我不知道薄弱点在哪", "看正确率和错题本", "沉淀错因、考点和答题习惯"],
  ["我不知道下一题练什么", "系统推题或随机刷题", "根据错因推荐下一步训练"],
  ["我时间很少", "自己筛题、自己总结", "把每次练习转化成复盘和行动"],
];

const audienceItems = [
  "已经听过课，但做题总是不稳定的人。",
  "选择题经常“看着都熟，但总选错”的人。",
  "案例题不知道怎么写，写完不知道能得几分的人。",
  "错题本很多，但不知道自己真正薄弱点的人。",
  "上班备考，时间有限，希望每次练习更有效的人。",
  "临近考试，需要快速找到丢分原因和答题模板的人。",
];

function SectionHeading({
  title,
  text,
  align = "left",
  index,
}: {
  title: string;
  text: string;
  align?: "left" | "center";
  index?: string;
}) {
  return (
    <div className={`${styles.sectionHeading} ${align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}`}>
      {index ? <p className={styles.sectionIndex}>{index}</p> : null}
      <h2 className="text-3xl font-black tracking-normal text-[#0a1110] text-pretty sm:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-8 text-[#52625f]">{text}</p>
    </div>
  );
}

function MiniProgramPreview() {
  return (
    <div className={styles.phoneScene} aria-label="微信小程序使用界面预览">
      <div className={styles.phoneHalo} aria-hidden="true" />
      <div className={styles.phoneFrame}>
        <div className={styles.phoneNotch} aria-hidden="true" />
        <div className={styles.phoneScreen}>
          <div className={styles.phoneAurora} aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className={styles.miniChatNav}>
            <span>‹ 返回首页</span>
            <strong>鲁班智考</strong>
            <em>＋</em>
          </div>
          <div className={styles.miniChatScroll}>
            <div className={styles.miniDateTag}>今天 11:02</div>
            <div className={styles.miniAiBubble}>
              <div className={styles.miniThinking}>
                <span />
                专属陪考教练已接入
              </div>
              <p>把你刚写的案例题答案发给我，我会按采分点批改，并记住你这次的丢分原因。</p>
            </div>
            <div className={styles.miniUserBubble}>
              施工单位应该加强现场安全管理，做好检查，发现问题及时整改。
            </div>
            <div className={styles.miniAiBubble}>
              <div className={styles.miniThinking}>
                <span />
                AI 正在按采分点批改
              </div>
              <div className={styles.miniWorkflow}>
                {["识别作答", "匹配采分点", "沉淀错因"].map((item, index) => (
                  <div key={item}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    {item}
                  </div>
                ))}
              </div>
              <div className={styles.miniScoreGrid}>
                <span>命中 2</span>
                <span>漏点 3</span>
                <span>表达泛</span>
              </div>
              <p>方向对，但表达过泛。缺少“专项施工方案、审核审批、专家论证、安全技术交底、检查验收、整改闭环”等程序性采分点。</p>
              <div className={styles.miniCoachNote}>
                已记录到你的陪考画像：程序性采分点表达不完整。下一题优先练“危大工程专项施工方案”。
              </div>
            </div>
          </div>
          <div className={styles.miniComposer} aria-hidden="true">
            <span>继续追问这道题...</span>
            <div>
              <em>智能</em>
              <button type="button" aria-label="发送">▶</button>
            </div>
          </div>
        </div>
      </div>
      <div className={styles.phoneCaption}>
        <span>微信小程序对话页</span>
        <strong>真实使用以手机端陪考对话为主</strong>
      </div>
    </div>
  );
}

function HeroDemo() {
  return (
    <div className={`${styles.demoShell} rounded-lg border border-[#d7e3df] bg-white shadow-[0_24px_80px_rgba(15,45,42,0.10)]`}>
      <div className={styles.scanBeam} aria-hidden="true" />
      <div className="flex items-center justify-between gap-4 border-b border-[#e4ece9] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#007f78] text-white">
            <Bot className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-black text-[#101820]">鲁班智考</p>
            <p className="truncate text-xs text-[#60706c]">AI 实务教练正在批改</p>
          </div>
        </div>
        <div className="hidden items-center gap-2 rounded-md bg-[#eef8f6] px-3 py-1.5 text-xs font-black text-[#007f78] sm:flex">
          <span className={styles.liveDot} aria-hidden="true" />
          案例题阅卷
        </div>
      </div>

      <div className={styles.gradingRail} aria-hidden="true">
        {["作答识别", "采分匹配", "错因诊断", "表达改写"].map((item, index) => (
          <div key={item} className={styles.gradingStep}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            {item}
          </div>
        ))}
      </div>

      <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="border-b border-[#e4ece9] p-5 lg:border-b-0 lg:border-r">
          <p className="text-xs font-black text-[#60706c]">你的答案</p>
          <div className={`${styles.answerCard} mt-4 rounded-lg border border-[#dfe8e5] bg-[#fbfdfc] p-4 text-sm leading-7 text-[#30433f]`}>
            施工单位应该加强现场安全管理，做好检查，发现问题及时整改。
          </div>
          <div className={styles.scoreTape} aria-hidden="true">
            <span>表达过泛</span>
            <span>漏程序</span>
            <span>可部分得分</span>
          </div>
          <div className={`${styles.warningCard} mt-4 rounded-lg border border-[#f0dfba] bg-[#fff8e7] p-4`}>
            <p className="text-xs font-black text-[#a86500]">主要问题</p>
            <p className="mt-2 text-sm leading-7 text-[#6d5a35]">
              方向对，但表达过泛，不能替代“专项施工方案、审核审批、专家论证、安全技术交底、检查验收、整改闭环”等程序性采分点。
            </p>
          </div>
        </div>

        <div className="p-5">
          <p className="text-xs font-black text-[#007f78]">改写成得分表达</p>
          <div className={`${styles.rewriteCard} mt-4 rounded-lg border border-[#b6ddd8] bg-[#f3fbfa] p-4 text-sm leading-7 text-[#17322f]`}>
            该做法不妥。施工单位应编制专项施工方案，并按规定履行审核、审批程序；超过一定规模的危大工程应组织专家论证。方案实施前应进行安全技术交底，实施过程中应按方案施工并检查验收，发现问题及时整改闭环。
          </div>
          <div className={styles.markerStack} aria-hidden="true">
            <span>专项施工方案</span>
            <span>专家论证</span>
            <span>技术交底</span>
            <span>整改闭环</span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {["命中少", "表达泛", "漏程序"].map((label) => (
              <div key={label} className={`${styles.signalChip} rounded-md border border-[#e4ece9] bg-white px-3 py-2 text-center text-xs font-black text-[#40514e]`}>
                {label}
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-[#dfe8e5] bg-white p-4">
            <p className="text-xs font-black text-[#60706c]">下一题建议</p>
            <p className="mt-2 text-sm leading-7 text-[#40514e]">
              继续训练“危大工程专项施工方案”类案例题，重点练习程序性采分点的完整表达。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function IntroPage() {
  return (
    <div className={`${styles.page} h-screen overflow-y-auto overflow-x-hidden bg-[#f7faf9] text-[#101820] [color-scheme:light] [-webkit-tap-highlight-color:transparent]`}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-[#101820] focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-white"
      >
        跳到主要内容
      </a>

      <header className="sticky top-0 z-40 border-b border-[#dfe8e5] bg-white/92 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <Link
            href="/intro"
            className="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
            aria-label="鲁班智考首页"
          >
            <Image src="/logo.png" alt="鲁班智考" width={36} height={36} priority />
            <span className="truncate text-xl font-black tracking-normal">鲁班智考</span>
          </Link>
          <nav className="hidden items-center gap-7 md:flex" aria-label="页面导航">
            {navItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-md text-sm font-bold text-[#40514e] transition-colors duration-150 hover:text-[#007f78] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                {item.label}
              </a>
            ))}
          </nav>
          <Link
            href="/invite-test"
            className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[#007f78] px-4 py-2.5 text-sm font-bold text-white shadow-sm transition-colors duration-150 hover:bg-[#00665f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
          >
            申请内测体验
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </header>

      <main id="main-content">
        <section className={`${styles.heroSection} mx-auto grid max-w-7xl items-center gap-8 px-5 pb-8 pt-10 sm:px-8 sm:pb-14 sm:pt-14 lg:grid-cols-[0.82fr_1.18fr] lg:gap-12 lg:pb-20 lg:pt-20`}>
          <div className={styles.heroPosterShapes} aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className={styles.heroCopy}>
            <p className={styles.heroKicker}>AI PRACTICAL COACH / CASE GRADING</p>
            <div className={styles.verticalMark} aria-hidden="true">实务教练</div>
            <h1 className={`${styles.heroTitle} text-4xl font-black leading-[1.05] tracking-normal text-pretty text-[#07100f] sm:text-6xl lg:text-7xl`}>
              题刷了很多，分数却不涨？
            </h1>
            <p className={`${styles.heroLead} mt-5 max-w-2xl text-2xl font-black leading-tight text-[#0f1f1d] text-pretty sm:text-3xl`}>
              你缺的不是更多题，而是有人告诉你为什么丢分。
            </p>
            <p className="mt-5 max-w-2xl text-base leading-8 text-[#52625f] sm:text-lg">
              鲁班智考是一建建筑实务专属个性化 AI 陪考教练。它不只是给你答案，而是持续记住你的作答习惯、薄弱考点和丢分原因，越用越懂你，并告诉你下一题该练什么。
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/invite-test"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-[#007f78] px-6 py-3.5 text-base font-black text-white shadow-sm transition-colors duration-150 hover:bg-[#00665f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                申请内测体验
                <ClipboardCheck className="h-5 w-5" aria-hidden="true" />
              </Link>
              <a
                href="#coach"
                className="inline-flex items-center justify-center gap-2 rounded-md border border-[#007f78] bg-white px-6 py-3.5 text-base font-black text-[#007f78] transition-colors duration-150 hover:bg-[#eef8f6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                看看陪考教练怎么懂你
                <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </a>
            </div>
            <div className="mt-7 grid gap-3 text-sm font-semibold text-[#52625f] sm:grid-cols-3">
              {[
                "案例题：按采分点批改，指出你的漏分原因",
                "选择题：分析干扰项，沉淀你的错因画像",
                "错题复盘：把每次错误变成专属训练计划",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-[#007f78]" aria-hidden="true" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
            <div className={styles.heroSignalRail} aria-hidden="true">
              {heroSignals.map((item, index) => (
                <span key={item}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {item}
                </span>
              ))}
            </div>
            <div className={styles.heroFlow} aria-hidden="true">
              {heroFlow.map((item, index) => (
                <div key={item}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {item}
                </div>
              ))}
            </div>
          </div>
          <div className={`${styles.heroVisual} hidden lg:block`}>
            <MiniProgramPreview />
          </div>
        </section>

        <section id="pain" className={`${styles.sectionPanel} scroll-mt-24 border-y border-[#dfe8e5] bg-white px-5 py-16 sm:px-8`}>
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              index="01"
              title="你是不是也这样备考？"
              text="鲁班智考要解决的，不是再给你一堆题，而是让每一次练习都变成一次提分诊断。"
            />
            <div className={`${styles.painGrid} mt-10 grid gap-3 lg:grid-cols-5`}>
              {painItems.map((item, index) => (
                <div key={item} className={`${styles.liftCard} rounded-lg border border-[#e4ece9] bg-[#fbfdfc] p-5`}>
                  <span className={styles.cardNumber}>{String(index + 1).padStart(2, "0")}</span>
                  <Lightbulb className="h-5 w-5 text-[#007f78]" aria-hidden="true" />
                  <p className="mt-4 text-sm font-bold leading-7 text-[#30433f]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="grading" className="scroll-mt-24 px-5 py-16 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              index="02"
              title="不只是 AI 解析，而是专属 AI 陪考教练"
              text="普通题库把 AI 放在解析后面。鲁班智考围绕你的真实作答持续工作：批改、诊断、改写、复盘、记住你的薄弱点，再推荐下一题。"
            />
            <div className={`${styles.featureGrid} mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-3`}>
              {featureItems.map((item) => {
                const Icon = item.icon;
                return (
                  <article key={item.title} className={`${styles.featureCard} rounded-lg border border-[#dfe8e5] bg-white p-6`}>
                    <div className={styles.iconBox}>
                      <Icon className="h-6 w-6 text-[#007f78]" aria-hidden="true" />
                    </div>
                    <h3 className="mt-5 text-xl font-black text-[#17322f]">{item.title}</h3>
                    <p className="mt-4 text-sm leading-7 text-[#52625f]">{item.text}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="coach" className={`${styles.coachBand} scroll-mt-24 bg-white px-5 py-16 sm:px-8`}>
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div>
              <SectionHeading
                index="03"
                title="一个越用越懂你的建筑实务陪考专家"
                text="鲁班智考会识别概念讲解、选择题讲解、选择题批改、案例题讲解、案例题阅卷和错题复盘。不同场景调用不同策略，同时把你的薄弱考点、表达习惯和错因持续沉淀下来。"
              />
              <div className="mt-8 rounded-lg border border-[#dfe8e5] bg-[#fbfdfc] p-5">
                <p className="text-sm font-black text-[#17322f]">为什么说它是陪考教练</p>
                <p className="mt-3 text-sm leading-7 text-[#52625f]">
                  它不是一次性答疑工具，而是围绕你每次作答建立个人学习画像：你常在哪些考点丢分、案例题表达哪里不像考试答案、下一轮应该优先练什么。
                </p>
              </div>
            </div>

            <div className={`${styles.stepGrid} grid gap-4 sm:grid-cols-2`}>
              {coachSteps.map((item, index) => {
                const Icon = item.icon;
                return (
                  <article key={item.title} className={`${styles.stepCard} rounded-lg border border-[#dfe8e5] bg-[#fbfdfc] p-6`}>
                    <span className={styles.stepIndex}>{String(index + 1).padStart(2, "0")}</span>
                    <Icon className="h-7 w-7 text-[#007f78]" aria-hidden="true" />
                    <h3 className="mt-5 text-xl font-black text-[#17322f]">{item.title}</h3>
                    <p className="mt-3 text-sm leading-7 text-[#52625f]">{item.text}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="compare" className="scroll-mt-24 px-5 py-16 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              index="04"
              title="为什么不是普通 AI 题库？"
              text="普通题库解决“有没有题”。鲁班智考解决“为什么丢分、怎么拿分”，并在每次练习后更懂你的备考状态。"
            />
            <div className={`${styles.compareTable} mt-10 overflow-hidden rounded-lg border border-[#dfe8e5] bg-white`}>
              <div className={styles.compareFlag} aria-hidden="true">AI 实务教练</div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                  <thead className="bg-[#f3f8f7] text-[#17322f]">
                    <tr>
                      <th scope="col" className="px-5 py-4 font-black">学员需求</th>
                      <th scope="col" className="px-5 py-4 font-black">普通题库 / AI 解析</th>
                      <th scope="col" className="px-5 py-4 font-black">鲁班智考</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e4ece9]">
                    {comparisonRows.map(([need, common, luban]) => (
                      <tr key={need}>
                        <th scope="row" className="px-5 py-4 font-black text-[#17322f]">{need}</th>
                        <td className="px-5 py-4 text-[#60706c]">{common}</td>
                        <td className="px-5 py-4 font-bold text-[#0b4e49]">{luban}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        <section id="demo" className="scroll-mt-24 bg-white px-5 py-16 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              index="05"
              title="看一次批改，你就知道差别"
              text="学员最有感知的不是“AI 很聪明”，而是看到自己原来写的不是答案，只是口号。"
              align="center"
            />
            <div className="mt-10">
              <HeroDemo />
            </div>
          </div>
        </section>

        <section className="px-5 py-16 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeading
              index="06"
              title="谁最适合用鲁班智考？"
              text="尤其适合已经学过一轮、刷题卡住、案例题不会写，想要一个持续记住自己薄弱点的专属陪考教练的人。"
            />
            <div className={`${styles.audienceGrid} mt-10 grid gap-3 md:grid-cols-2 lg:grid-cols-3`}>
              {audienceItems.map((item) => (
                <div key={item} className={`${styles.audienceCard} flex gap-3 rounded-lg border border-[#dfe8e5] bg-white p-5`}>
                  <GraduationCap className="mt-0.5 h-5 w-5 shrink-0 text-[#007f78]" aria-hidden="true" />
                  <p className="text-sm font-bold leading-7 text-[#40514e]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={`${styles.finalCta} bg-[#0c2d2a] px-5 py-16 text-white sm:px-8`}>
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <h2 className="text-3xl font-black tracking-normal text-pretty sm:text-4xl">
                申请加入内测，让 AI 陪考教练先认识你。
              </h2>
              <p className="mt-4 max-w-3xl text-base leading-8 text-white/74">
                提交内测申请后，把你最近做错的一道题交给鲁班智考。它会从第一次批改开始记录你的丢分原因、表达习惯和下一步训练方向。
              </p>
              <p className="mt-4 max-w-3xl text-xs leading-6 text-white/54">
                适用于一建/二建建筑实务备考场景。学习效果与个人基础、学习投入和使用频率有关。
              </p>
            </div>
            <Link
              href="/invite-test"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-white px-6 py-3.5 text-base font-black text-[#0c2d2a] transition-colors duration-150 hover:bg-[#eef8f6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              申请内测体验
              <Sparkles className="h-5 w-5" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-[#dfe8e5] bg-[#f7faf9] px-5 py-10 sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-black text-[#17322f]">鲁班智考</p>
            <p className="mt-2 text-sm text-[#60706c]">
              由 <span translate="no">DeepTutor</span> agent-native 学习系统提供底层能力。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href="#demo"
              className="rounded-md border border-[#dfe8e5] bg-white px-4 py-2.5 text-sm font-bold text-[#40514e] transition-colors duration-150 hover:bg-[#eef8f6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
            >
              查看批改 Demo
            </a>
            <Link
              href="/invite-test"
              className="rounded-md bg-[#007f78] px-4 py-2.5 text-sm font-bold text-white transition-colors duration-150 hover:bg-[#00665f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
            >
              申请内测体验
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
