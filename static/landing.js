/* ============================================================================
   BidProof 产品页首屏底纹  —  直接替换 static/landing.js

   与旧版的区别：
   1. 旧版是常驻 requestAnimationFrame 循环（30fps 不停画整屏网格 + 三份文档 +
      贝塞尔路径 + 脉冲节点），只要首屏在视口内就一直烧 CPU。新版只在加载时跑
      一次约 1.9 秒的扫描，结束后主动 cancelAnimationFrame，之后只有指针移动
      才会补一帧。
   2. 旧版是深色科幻场景，和登录后的浅色工作台完全不是一个产品。新版画的是一页
      招标文件：纸面、栏线、条款块，扫描线经过时留下两处定位标记（青绿=已匹配，
      印章红=缺证据）。它说明的正是这个产品做的事。
   3. 底纹对比度压到很低，首屏文字始终可读；它是背景不是主角。
   ========================================================================== */

(() => {
  "use strict";

  const canvas = document.querySelector("#hero-evidence-canvas");
  const hero = canvas?.closest(".hero");
  if (!canvas || !hero) return;

  const context = canvas.getContext("2d", { alpha: false });
  if (!context) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const palette = {
    paper: "#f5f7f6",
    rule: "rgba(20, 32, 38, 0.055)",
    ruleStrong: "rgba(20, 32, 38, 0.10)",
    margin: "rgba(20, 32, 38, 0.09)",
    matchFill: "rgba(8, 127, 114, 0.09)",
    matchLine: "rgba(8, 127, 114, 0.38)",
    missFill: "rgba(173, 33, 27, 0.08)",
    missLine: "rgba(173, 33, 27, 0.34)",
    beam: "rgba(8, 127, 114, 0.26)",
    beamGlow: "rgba(8, 127, 114, 0.045)",
  };

  const SWEEP_MS = 1500;
  const SETTLE_MS = 420;

  const viewport = { width: 0, height: 0, dpr: 1 };
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };
  const scene = { columnX: 0, columnWidth: 0, top: 0, bottom: 0, lines: [], marks: [] };

  let animationFrame = 0;
  let sweepStart = 0;
  let pendingFrame = 0;

  /* ------------------------------------------------------------ 场景构建 */

  function buildScene() {
    const { width, height } = viewport;
    const compact = width < 900;

    /* 纸面跟着证据卡片走：卡片就是压在这页纸上的。这样窄屏时纸面被卡片盖住，
       不会铺到标题和正文底下去，只在四周留一点页边。 */
    const card = hero.querySelector(".evidence-stack");
    const heroBox = hero.getBoundingClientRect();
    let top = height * 0.12;
    let bottom = height - 24;

    if (card) {
      const box = card.getBoundingClientRect();
      scene.columnX = box.left - heroBox.left - 34;
      scene.columnWidth = width - scene.columnX + 40;
      const bleed = compact ? 22 : 72;
      top = Math.max(10, box.top - heroBox.top - bleed);
      bottom = Math.min(height - 8, box.bottom - heroBox.top + bleed);
    } else {
      scene.columnX = compact ? width * 0.06 : width * 0.52;
      scene.columnWidth = width - scene.columnX + 40;
    }

    scene.lines = [];
    const lineGap = compact ? 21 : 24;
    let index = 0;
    for (let y = top; y < bottom; y += lineGap, index += 1) {
      /* 每 9 行留一个空行，模拟条款之间的段落间隔 */
      if (index % 9 === 8) continue;
      const factor = 0.42 + ((index * 37) % 52) / 100;
      scene.lines.push({
        y: Math.round(y),
        width: scene.columnWidth * factor,
        heavy: index % 9 === 0,
      });
    }

    /* 两处定位：一处匹配上了，一处没有。它们是扫描线经过后才出现的 */
    const span = bottom - top;
    const blockHeight = Math.max(44, Math.min(72, span * 0.16));
    scene.marks = [
      { y: top + span * 0.16, height: blockHeight, fill: palette.matchFill, line: palette.matchLine, at: 0.34 },
      { y: top + span * 0.62, height: blockHeight, fill: palette.missFill, line: palette.missLine, at: 0.66 },
    ].filter((mark) => mark.y + mark.height < bottom);

    scene.top = top;
    scene.bottom = bottom;
  }

  /* -------------------------------------------------------------- 绘制 */

  function roundedRect(x, y, width, height, radius) {
    const safe = Math.max(0, Math.min(radius, width / 2, height / 2));
    context.beginPath();
    context.roundRect(x, y, width, height, safe);
  }

  function drawScene(progress) {
    const { width, height } = viewport;
    if (!width || !height) return;

    const shiftX = pointer.x;
    const shiftY = pointer.y;

    context.fillStyle = palette.paper;
    context.fillRect(0, 0, width, height);

    const left = scene.columnX + shiftX;

    /* 页边留白处的一条竖线，招标文件的装订边。只在纸面范围内出现 */
    const pageTop = scene.top + shiftY;
    const pageHeight = Math.max(0, scene.bottom - scene.top);
    context.fillStyle = palette.margin;
    context.fillRect(Math.round(left - 22) + 0.5, Math.round(pageTop), 1, Math.round(pageHeight));

    /* 正文行。扫描线还没走到的部分不画，形成「逐页读过去」的效果 */
    const revealX = left - 22 + (width - left + 22) * progress;
    for (const line of scene.lines) {
      const y = Math.round(line.y + shiftY);
      const drawn = Math.min(line.width, Math.max(0, revealX - left));
      if (drawn <= 0) continue;
      context.fillStyle = line.heavy ? palette.ruleStrong : palette.rule;
      context.fillRect(Math.round(left), y, Math.round(drawn), line.heavy ? 3 : 2);
    }

    /* 定位标记：扫描线越过它的位置之后才浮现 */
    for (const mark of scene.marks) {
      if (progress <= mark.at) continue;
      const alpha = Math.min(1, (progress - mark.at) / 0.16);
      const y = mark.y + shiftY;
      context.save();
      context.globalAlpha = alpha;
      roundedRect(left - 10, y, scene.columnWidth + 20, mark.height, 6);
      context.fillStyle = mark.fill;
      context.fill();
      context.strokeStyle = mark.line;
      context.lineWidth = 1;
      context.stroke();
      context.restore();
    }

    /* 扫描线本身，走完就不再出现 */
    if (progress > 0 && progress < 1) {
      const beamX = Math.round(revealX);
      context.fillStyle = palette.beamGlow;
      context.fillRect(beamX - 30, pageTop - 14, 60, pageHeight + 28);
      context.fillStyle = palette.beam;
      context.fillRect(beamX, pageTop - 14, 1, pageHeight + 28);
    }
  }

  /* ------------------------------------------------------------ 动画调度 */

  function easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function step(now) {
    const elapsed = now - sweepStart;
    const raw = Math.min(1, elapsed / SWEEP_MS);
    drawScene(easeOut(raw));
    if (elapsed < SWEEP_MS + SETTLE_MS) {
      animationFrame = requestAnimationFrame(step);
    } else {
      /* 扫描结束就停手，不留常驻循环 */
      cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      drawScene(1);
    }
  }

  function play() {
    cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    if (reduceMotion.matches) {
      drawScene(1);
      return;
    }
    sweepStart = performance.now();
    animationFrame = requestAnimationFrame(step);
  }

  /* 指针视差只补一帧，不开循环 */
  function scheduleRepaint() {
    if (animationFrame || pendingFrame) return;
    pendingFrame = requestAnimationFrame(() => {
      pendingFrame = 0;
      pointer.x = pointer.targetX;
      pointer.y = pointer.targetY;
      drawScene(1);
    });
  }

  function resize() {
    const bounds = hero.getBoundingClientRect();
    viewport.width = Math.max(1, Math.round(bounds.width));
    viewport.height = Math.max(1, Math.round(bounds.height));
    viewport.dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(viewport.width * viewport.dpr);
    canvas.height = Math.round(viewport.height * viewport.dpr);
    context.setTransform(viewport.dpr, 0, 0, viewport.dpr, 0, 0);
    buildScene();
    if (!animationFrame) drawScene(1);
  }

  hero.addEventListener("pointermove", (event) => {
    if (reduceMotion.matches) return;
    const bounds = hero.getBoundingClientRect();
    pointer.targetX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 10;
    pointer.targetY = ((event.clientY - bounds.top) / bounds.height - 0.5) * 7;
    scheduleRepaint();
  }, { passive: true });

  hero.addEventListener("pointerleave", () => {
    pointer.targetX = 0;
    pointer.targetY = 0;
    scheduleRepaint();
  }, { passive: true });

  reduceMotion.addEventListener("change", play);

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(hero);

  /* 首屏不在视口内（比如带锚点进来）就不放动画，直接给终态 */
  const visibilityObserver = new IntersectionObserver(([entry], observer) => {
    if (!entry.isIntersecting) return;
    observer.disconnect();
    play();
  }, { threshold: 0.15 });

  resize();
  drawScene(0);
  visibilityObserver.observe(hero);
})();
