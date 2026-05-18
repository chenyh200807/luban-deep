/* eslint-disable i18n/no-literal-ui-text -- Chinese-only product landing page. */
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import styles from "./intro.module.css";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  GraduationCap,
  Lightbulb,
  PenLine,
  Route,
  Sparkles,
  Target,
} from "lucide-react";

export const metadata: Metadata = {
  title: "鲁班智考 AI 实务教练",
  description: "鲁班智考是越用越懂你的专属个性化 AI 陪考教练，帮你批改作答、拆解采分点、诊断错因，并规划下一步训练。",
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

const heroSignals = ["案例批改", "错因画像", "专属训练"];

const coachSteps = [
  { icon: ClipboardCheck, title: "批改作答", text: "按采分点拆命中、漏点和表达问题。" },
  { icon: Target, title: "诊断错因", text: "区分概念混淆、审题失误、干扰项误导和关键词漏看。" },
  { icon: PenLine, title: "改写表达", text: "把口号式答案改成更像考试答案的短句和分点。" },
  { icon: Route, title: "陪你规划", text: "根据你的错因画像，把每次错题转化成下一步训练方向。" },
];

const gradingJourney = [
  {
    label: "你的作答",
    title: "先看真实答案",
    text: "不看你有没有背会术语，先看你实际写出来的句子。",
  },
  {
    label: "AI 批改",
    title: "逐条对照采分点",
    text: "标出命中、漏点、部分得分和表达过泛的位置。",
  },
  {
    label: "陪考画像",
    title: "沉淀你的错因",
    text: "记录你常漏的程序、概念混淆和案例题表达习惯。",
  },
  {
    label: "下一题",
    title: "生成专属训练方向",
    text: "把这次错题变成下一轮更精准的练习计划。",
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

const inviteTestHref = "/invite-test/apply?utm_source=intro&utm_campaign=landing_page";

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
          <div className={styles.realMiniTopbar}>
            <div className={styles.realMiniBrand}>
              <Image src="/images/logo-white.png" alt="" width={135} height={151} aria-hidden="true" />
            </div>
            <span className={styles.realBackPill}>‹ 返回首页</span>
            <div className={styles.realMiniActions} aria-hidden="true">
              <span>✎</span>
              <span>•••</span>
              <span className={styles.realWechatCapsule}>
                <i>•••</i>
                <i />
              </span>
            </div>
          </div>

          <div className={styles.realMiniScroll}>
            <article className={styles.realMiniArticle}>
              <p className={styles.realMiniLead}>
                好，我直接给你一建建筑实务核心考点框架，按章节模块、高频题型和拿分策略来排。
              </p>
              <h3>核心考点框架</h3>
              <section>
                <h4>3. 施工技术（案例题主力）</h4>
                <div className={styles.realMiniTable} role="presentation">
                  <div>模块</div>
                  <div>核心考点</div>
                  <div>题型</div>
                  <div>测量</div>
                  <div>施工测量方法、轴线投测、标高传递</div>
                  <div>选择题</div>
                  <div>土方</div>
                  <div>基坑支护、降水方法、验槽程序、回填要求</div>
                  <div>案例题</div>
                  <div>地基与基础</div>
                  <div>桩基施工、大体积混凝土裂缝控制</div>
                  <div>案例题高频</div>
                </div>
              </section>

              <div className={styles.realMiniCalloutError}>
                <span>易错点</span>
                <p>危大工程与超过一定规模危大工程的论证程序容易混；网络计划中总时差计算容易漏。</p>
              </div>

              <section>
                <h4>5. 法规与标准（选择题 + 案例题补充）</h4>
                <ul>
                  <li>危险性较大的分部分项工程安全管理规定</li>
                  <li>建设工程质量管理条例</li>
                  <li>绿色建筑评价标准、节能验收标准</li>
                </ul>
              </section>

              <div className={styles.realMiniCalloutScore}>
                <span>踩分点</span>
                <p>法规题考程序性规定：谁审批、谁论证、多少天，不考条文全文。</p>
              </div>
            </article>
          </div>

          <div className={styles.realMiniComposer} aria-hidden="true">
            <span>继续追问...</span>
            <div className={styles.realMiniModes}>
              <em>智能</em>
              <em>深度</em>
              <em>快速</em>
              <em>◎ 联网</em>
            </div>
            <b>▶</b>
          </div>
          <div className={styles.realMiniTabbar} aria-hidden="true">
            {["对话", "历史", "学情", "我的"].map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </div>
      </div>
      <div className={styles.phoneCaption}>
        <span>微信小程序真实对话页</span>
        <strong>长文回答、表格、易错点和踩分点</strong>
      </div>
    </div>
  );
}

function ChatProof() {
  return (
    <div className={styles.chatProof}>
      <div className={styles.chatProofHeader}>
        <span>微信小程序真实对话截面</span>
        <strong>不是一条 AI 解析，而是一位越用越懂你的陪考教练</strong>
      </div>
      <div className={styles.chatProofBody}>
        <div className={styles.proofMiniPhone}>
          <div className={styles.proofMiniBar}>
            <span>‹ 返回首页</span>
            <strong>鲁班智考</strong>
            <em>•••</em>
          </div>
          <div className={styles.proofMiniContent}>
            <p>好，我直接按“章节模块 + 高频题型 + 拿分策略”给你梳理。</p>
            <h3>4. 项目管理实务（案例题主力）</h3>
            <ul>
              <li>进度管理：网络计划、总时差、关键线路</li>
              <li>安全管理：危大工程、专项施工方案、技术交底</li>
              <li>现场管理：施工平面布置、消防、环保、文明施工</li>
            </ul>
            <div className={styles.proofErrorCard}>
              <span>易错点</span>
              <p>危大工程与超过一定规模危大工程的论证程序容易混；索赔事件的责任归属判断不清晰。</p>
            </div>
            <div className={styles.proofScoreCard}>
              <span>踩分点</span>
              <p>案例题要写程序性采分点：谁编制、谁审批、是否专家论证、交底和验收如何闭环。</p>
            </div>
          </div>
          <div className={styles.proofMiniComposer}>
            <span>继续追问...</span>
            <em>快速</em>
            <b>▶</b>
          </div>
        </div>

        <div className={styles.proofCoachPanel}>
          <span>陪考教练价值</span>
          <h3>它会把这次对话沉淀成你的个人学习画像</h3>
          <p>
            不是用完即走的问答，而是持续记录你常混的程序、容易漏写的采分点和案例题表达习惯，让下一次讲解、批改和推荐更贴近你。
          </p>
          <div className={styles.proofCoachGrid}>
            <div>
              <b>01</b>
              <strong>识别薄弱考点</strong>
            </div>
            <div>
              <b>02</b>
              <strong>记录错因画像</strong>
            </div>
            <div>
              <b>03</b>
              <strong>推荐下一题</strong>
            </div>
          </div>
          <Link href={inviteTestHref} className={styles.proofApplyLink}>
            申请内测体验
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
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
        className={styles.skipLink}
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
            <span className={styles.headerLogoTile}>
              <Image src="/images/logo-white.png" alt="" width={135} height={151} priority />
            </span>
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
            href={inviteTestHref}
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
            <p className={styles.heroBrand}>鲁班智考</p>
            <p className={styles.heroKicker}>AI PRACTICAL COACH / CASE GRADING</p>
            <div className={styles.verticalMark} aria-hidden="true">实务教练</div>
            <h1 className={`${styles.heroTitle} text-4xl font-black leading-[1.05] tracking-normal text-pretty text-[#07100f] sm:text-6xl lg:text-7xl`}>
              题刷了很多，分数却不涨？
            </h1>
            <p className={`${styles.heroLead} mt-5 max-w-2xl text-2xl font-black leading-tight text-[#0f1f1d] text-pretty sm:text-3xl`}>
              你缺的不是更多题，而是有人告诉你为什么丢分。
            </p>
            <p className="mt-5 max-w-2xl text-base leading-8 text-[#52625f] sm:text-lg">
              专为一建建筑实务打造的个性化 AI 陪考教练。它会持续记住你的作答习惯、薄弱考点和丢分原因，越用越懂你。
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link
                href={inviteTestHref}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-[#007f78] px-6 py-3.5 text-base font-black text-white shadow-sm transition-colors duration-150 hover:bg-[#00665f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                申请内测体验
                <ClipboardCheck className="h-5 w-5" aria-hidden="true" />
              </Link>
              <a
                href="#demo"
                className="inline-flex items-center justify-center gap-2 rounded-md border border-[#007f78] bg-white px-6 py-3.5 text-base font-black text-[#007f78] transition-colors duration-150 hover:bg-[#eef8f6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                看一次 AI 批改
                <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </a>
            </div>
            <div className={styles.heroProofs}>
              {heroSignals.map((item) => (
                <div key={item}>
                  <CheckCircle2 className="h-4 w-4 text-[#007f78]" aria-hidden="true" />
                  <span>{item}</span>
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
              title="一道错题，怎么变成下一步训练？"
              text="鲁班智考不是继续塞题，而是把你的真实作答转成可执行的提分动作。"
            />
            <div className={styles.journeyTrack}>
              {gradingJourney.map((item, index) => (
                <article key={item.title} className={styles.journeyItem}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <p>{item.label}</p>
                  <h3>{item.title}</h3>
                  <small>{item.text}</small>
                </article>
              ))}
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
              title="看一次对话批改，你就知道差别"
              text="真正有说服力的不是功能列表，而是你看到自己的答案如何被拆成得分点、漏分点和下一题。"
              align="center"
            />
            <div className="mt-10">
              <ChatProof />
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

        <section className="border-y border-[#dfe8e5] bg-white px-5 py-16 sm:px-8">
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.86fr_1.14fr] lg:items-center">
            <div>
              <p className={styles.sectionIndex}>07</p>
              <h2 className="text-3xl font-black tracking-normal text-[#0a1110] text-pretty sm:text-4xl">
                现在申请内测，让 AI 陪考教练先认识你
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-8 text-[#52625f]">
                首批内测不是公开注册。我们会优先邀请正在备考建筑实务、愿意提交真实错题和反馈体验的学员。
              </p>
            </div>
            <div className="rounded-lg border border-[#dfe8e5] bg-[#f7faf9] p-6">
              <p className="text-sm font-black text-[#17322f]">申请信息会用来判断三件事</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                {["你卡在哪", "是否适合首批体验", "下一步优先打磨什么"].map((item, index) => (
                  <div key={item} className="rounded-md border border-[#d7e3df] bg-white p-4">
                    <span className="text-xs font-black text-[#007f78]">{String(index + 1).padStart(2, "0")}</span>
                    <p className="mt-3 text-sm font-bold leading-6 text-[#30433f]">{item}</p>
                  </div>
                ))}
              </div>
              <Link
                href={inviteTestHref}
                className="mt-6 inline-flex items-center justify-center gap-2 rounded-md bg-[#007f78] px-5 py-3 text-sm font-black text-white transition-colors duration-150 hover:bg-[#00665f] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#007f78]"
              >
                申请内测体验
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
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
              href={inviteTestHref}
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
              href={inviteTestHref}
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
