(() => {
  "use strict";

  const canvas = document.querySelector("#hero-evidence-canvas");
  const hero = canvas?.closest(".hero");
  if (!canvas || !hero) return;

  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };
  const viewport = { width: 0, height: 0, dpr: 1 };
  let animationFrame = 0;
  let startTime = performance.now();
  let lastDrawTime = 0;
  let heroIsVisible = true;

  const palette = {
    paper: "rgba(224, 236, 244, 0.08)",
    paperStroke: "rgba(155, 180, 199, 0.24)",
    rule: "rgba(173, 197, 212, 0.16)",
    grid: "rgba(131, 157, 178, 0.065)",
    teal: "rgba(77, 214, 197, 0.92)",
    tealSoft: "rgba(77, 214, 197, 0.18)",
    amber: "rgba(247, 190, 87, 0.88)",
    background: "#07111f",
  };

  function roundedRect(x, y, width, height, radius) {
    const safeRadius = Math.min(radius, width / 2, height / 2);
    context.beginPath();
    context.roundRect(x, y, width, height, safeRadius);
  }

  function drawGrid(width, height, offsetX, offsetY) {
    const gap = width < 600 ? 40 : 52;
    context.strokeStyle = palette.grid;
    context.lineWidth = 1;
    context.beginPath();
    for (let x = (offsetX % gap) - gap; x < width + gap; x += gap) {
      context.moveTo(Math.round(x) + 0.5, 0);
      context.lineTo(Math.round(x) + 0.5, height);
    }
    for (let y = (offsetY % gap) - gap; y < height + gap; y += gap) {
      context.moveTo(0, Math.round(y) + 0.5);
      context.lineTo(width, Math.round(y) + 0.5);
    }
    context.stroke();
  }

  function drawDocument(document, time, index) {
    const drift = Math.sin(time * 0.34 + index * 1.7) * 5;
    const x = document.x + pointer.x * document.depth;
    const y = document.y + drift + pointer.y * document.depth;

    context.save();
    context.translate(x, y);
    roundedRect(0, 0, document.width, document.height, 8);
    context.fillStyle = palette.paper;
    context.fill();
    context.strokeStyle = palette.paperStroke;
    context.lineWidth = 1;
    context.stroke();

    context.fillStyle = index === 1 ? palette.amber : palette.teal;
    context.fillRect(18, 19, 28, 3);

    const lineCount = Math.max(5, Math.floor(document.height / 25));
    for (let line = 0; line < lineCount; line += 1) {
      const top = 42 + line * 20;
      if (top > document.height - 18) break;
      const widthFactor = 0.52 + ((line * 37 + index * 19) % 36) / 100;
      context.fillStyle = palette.rule;
      context.fillRect(18, top, Math.max(36, (document.width - 36) * widthFactor), 2);
    }

    const locatorY = 72 + ((index * 53) % Math.max(30, document.height - 120));
    roundedRect(12, locatorY, document.width - 24, 31, 4);
    context.fillStyle = palette.tealSoft;
    context.fill();
    context.strokeStyle = index === 1 ? palette.amber : palette.teal;
    context.globalAlpha = 0.76;
    context.stroke();
    context.restore();

    return {
      x: x + document.width - 13,
      y: y + locatorY + 15,
      color: index === 1 ? palette.amber : palette.teal,
    };
  }

  function drawEvidencePath(from, to, time, index) {
    const controlX = from.x + (to.x - from.x) * 0.48;
    context.save();
    context.strokeStyle = "rgba(106, 180, 175, 0.27)";
    context.lineWidth = 1;
    context.setLineDash([5, 7]);
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.bezierCurveTo(controlX, from.y, controlX, to.y, to.x, to.y);
    context.stroke();
    context.setLineDash([]);

    const progress = (time * 0.16 + index * 0.28) % 1;
    const inverse = 1 - progress;
    const dotX = inverse ** 3 * from.x
      + 3 * inverse ** 2 * progress * controlX
      + 3 * inverse * progress ** 2 * controlX
      + progress ** 3 * to.x;
    const dotY = inverse ** 3 * from.y
      + 3 * inverse ** 2 * progress * from.y
      + 3 * inverse * progress ** 2 * to.y
      + progress ** 3 * to.y;
    context.fillStyle = from.color;
    context.beginPath();
    context.arc(dotX, dotY, 2.6, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }

  function drawDecisionNode(x, y, time) {
    const pulse = 1 + Math.sin(time * 1.9) * 0.08;
    context.save();
    context.translate(x + pointer.x * 0.3, y + pointer.y * 0.3);
    context.scale(pulse, pulse);
    context.fillStyle = "rgba(7, 17, 31, 0.86)";
    context.strokeStyle = palette.teal;
    context.lineWidth = 1.3;
    context.beginPath();
    context.arc(0, 0, 27, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.beginPath();
    context.moveTo(-9, 0);
    context.lineTo(-2, 7);
    context.lineTo(11, -8);
    context.strokeStyle = "rgba(194, 249, 240, 0.92)";
    context.lineWidth = 2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.stroke();
    context.restore();
  }

  function drawScan(width, height, time) {
    const sceneStart = width < 720 ? width * 0.08 : width * 0.46;
    const sceneWidth = width - sceneStart;
    const scanX = sceneStart + ((time * 42) % Math.max(1, sceneWidth));
    context.fillStyle = "rgba(77, 214, 197, 0.028)";
    context.fillRect(scanX - 34, 0, 68, height);
    context.fillStyle = "rgba(77, 214, 197, 0.34)";
    context.fillRect(Math.round(scanX), 0, 1, height);
  }

  function drawScene(milliseconds) {
    const width = viewport.width;
    const height = viewport.height;
    if (!width || !height) return;

    const time = (milliseconds - startTime) / 1000;
    pointer.x += (pointer.targetX - pointer.x) * 0.035;
    pointer.y += (pointer.targetY - pointer.y) * 0.035;

    context.clearRect(0, 0, width, height);
    context.fillStyle = palette.background;
    context.fillRect(0, 0, width, height);
    drawGrid(width, height, time * -2 + pointer.x * 0.12, time * 1.2 + pointer.y * 0.12);

    const compact = width < 720;
    const baseX = compact ? width * 0.46 : width * 0.58;
    const documentWidth = Math.max(116, Math.min(compact ? 142 : 186, width * 0.22));
    const documentHeight = compact ? 202 : 254;
    const documents = [
      { x: baseX, y: height * 0.12, width: documentWidth, height: documentHeight, depth: 0.14 },
      { x: baseX + documentWidth * 0.73, y: height * 0.34, width: documentWidth * 0.9, height: documentHeight * 0.82, depth: 0.24 },
      { x: baseX - documentWidth * 0.2, y: height * 0.61, width: documentWidth * 0.86, height: documentHeight * 0.72, depth: 0.1 },
    ];
    const sources = documents.map((document, index) => drawDocument(document, time, index));
    const decision = {
      x: compact ? width * 0.88 : width * 0.89,
      y: compact ? height * 0.72 : height * 0.5,
    };
    sources.forEach((source, index) => drawEvidencePath(source, decision, time, index));
    drawDecisionNode(decision.x, decision.y, time);
    drawScan(width, height, time);
  }

  function animate(milliseconds) {
    if (milliseconds - lastDrawTime >= 32) {
      drawScene(milliseconds);
      lastDrawTime = milliseconds;
    }
    animationFrame = requestAnimationFrame(animate);
  }

  function start() {
    cancelAnimationFrame(animationFrame);
    if (reduceMotion.matches || document.hidden || !heroIsVisible) {
      drawScene(startTime + 1800);
      return;
    }
    startTime = performance.now();
    animationFrame = requestAnimationFrame(animate);
  }

  function resize() {
    const bounds = hero.getBoundingClientRect();
    viewport.width = Math.max(1, Math.round(bounds.width));
    viewport.height = Math.max(1, Math.round(bounds.height));
    viewport.dpr = Math.min(window.devicePixelRatio || 1, 1.35);
    canvas.width = Math.round(viewport.width * viewport.dpr);
    canvas.height = Math.round(viewport.height * viewport.dpr);
    context.setTransform(viewport.dpr, 0, 0, viewport.dpr, 0, 0);
    drawScene(performance.now());
  }

  hero.addEventListener("pointermove", (event) => {
    const bounds = hero.getBoundingClientRect();
    pointer.targetX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 14;
    pointer.targetY = ((event.clientY - bounds.top) / bounds.height - 0.5) * 10;
  }, { passive: true });
  hero.addEventListener("pointerleave", () => {
    pointer.targetX = 0;
    pointer.targetY = 0;
  }, { passive: true });
  document.addEventListener("visibilitychange", start);
  reduceMotion.addEventListener("change", start);

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(hero);
  const visibilityObserver = new IntersectionObserver(([entry]) => {
    heroIsVisible = entry.isIntersecting;
    start();
  }, { threshold: 0.02 });
  visibilityObserver.observe(hero);
  resize();
  start();
})();
