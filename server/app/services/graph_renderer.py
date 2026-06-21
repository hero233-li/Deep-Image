"""将 deepimage-graph JSON 渲染为 matplotlib 图像"""

import json
import base64
import io
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, FancyArrowPatch
from app.utils.logger import logger


def parse_graph_json(text: str) -> dict | None:
    """从重建文本中提取 deepimage-graph JSON 块"""
    m = re.search(r'```deepimage-graph\s*\n([\s\S]*?)```', text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def render_to_base64(graph: dict) -> str:
    """渲染 deepimage-graph JSON 为 PNG base64"""
    gtype = graph.get("type", "mixed")
    title = graph.get("title", "")
    elements = graph.get("elements", [])

    if gtype == "function":
        return _render_functions(title, elements)
    elif gtype == "geometry":
        return _render_geometry(title, elements)
    else:
        return _render_mixed(title, elements)


def _render_geometry(title: str, elements: list) -> str:
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)
    ax.axhline(y=0, color='gray', lw=0.5)
    ax.axvline(x=0, color='gray', lw=0.5)

    # 收集所有点坐标确定范围
    points = {}
    xs, ys = [], []

    for el in elements:
        kind = el.get("kind", "")
        if kind == "point":
            name = el.get("label", "")
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            points[name] = (x, y)
            xs.append(x); ys.append(y)
        elif kind == "circle":
            cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 1))
            if el.get("label"):
                points[el["label"]] = (cx, cy)
            xs.extend([cx-r, cx+r]); ys.extend([cy-r, cy+r])

    if not xs:
        xs = [-1.5, 1.5]; ys = [-1.5, 1.5]

    margin = 0.5
    ax.set_xlim(min(xs)-margin, max(xs)+margin)
    ax.set_ylim(min(ys)-margin, max(ys)+margin)

    # 画圆
    for el in elements:
        if el.get("kind") == "circle":
            cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 1))
            theta = np.linspace(0, 2*np.pi, 300)
            ax.plot(cx + r*np.cos(theta), cy + r*np.sin(theta), 'k-', lw=1.5)

    # 画线
    for el in elements:
        if el.get("kind") == "line":
            a_name, b_name = el.get("from", ""), el.get("to", "")
            if a_name in points and b_name in points:
                a, b = points[a_name], points[b_name]
                style = el.get("style", "solid")
                ls = "--" if style == "dashed" else "-"
                color = el.get("color", "b")
                ax.plot([a[0], b[0]], [a[1], b[1]], color=color, ls=ls, lw=1.5)

    # 直角标记
    for el in elements:
        if el.get("kind") == "right_angle":
            at_name = el.get("at", "")
            if at_name in points:
                at = points[at_name]
                lines = el.get("lines", [])
                s = 0.08
                # 在点处画小方块
                ax.plot([at[0], at[0]+s], [at[1], at[1]], 'k-', lw=1)
                ax.plot([at[0], at[0]], [at[1], at[1]+s], 'k-', lw=1)

    # 角度弧
    for el in elements:
        if el.get("kind") == "angle":
            at_name = el.get("at", "O")
            from_name = el.get("from", "")
            to_name = el.get("to", "")
            if at_name in points and from_name in points and to_name in points:
                at = points[at_name]
                v1 = np.array(points[from_name]) - np.array(at)
                v2 = np.array(points[to_name]) - np.array(at)
                ang1 = np.arctan2(v1[1], v1[0])
                ang2 = np.arctan2(v2[1], v2[0])
                if ang2 < ang1:
                    ang2 += 2*np.pi
                r = 0.25
                arc_t = np.linspace(ang1, ang2, 40)
                ax.plot(at[0] + r*np.cos(arc_t), at[1] + r*np.sin(arc_t), 'k-', lw=1.2)
                label = el.get("label", "")
                if label:
                    mid = (ang1 + ang2) / 2
                    ax.text(at[0] + r*1.3*np.cos(mid), at[1] + r*1.3*np.sin(mid),
                            f'${label}$', fontsize=14, fontweight='bold')

    # 画点
    for name, (x, y) in points.items():
        ax.plot(x, y, 'ko', ms=6, zorder=5)
        ax.text(x+0.05, y+0.05, f'${name}$', fontsize=13)

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('$x$', fontsize=12)
    ax.set_ylabel('$y$', fontsize=12)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _render_functions(title: str, elements: list) -> str:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.grid(True, alpha=0.2)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.15)
    ax.set_xlabel('$x$', fontsize=12)
    ax.set_ylabel('$y$', fontsize=12)

    colors = ['blue', 'green', 'orange', 'red']
    labels = ['A', 'B', 'C', 'D']

    for i, el in enumerate(elements):
        if el.get("kind") != "curve":
            continue
        shape = el.get("shape", "single_peak")
        peak_y = float(el.get("peak_y", 1))
        zeros = el.get("zeros", [0, 1])
        zeros = [float(z) for z in zeros]
        label = el.get("label", labels[i])
        color = colors[i % 4]

        x = np.linspace(0, 1, 300)
        if shape == "single_peak":
            # 单峰：从0→peak→0
            peak_x = (zeros[0] + zeros[-1]) / 2
            y = np.zeros_like(x)
            for j in range(len(zeros)-1):
                mask = (x >= zeros[j]) & (x <= zeros[j+1])
                y[mask] = peak_y * np.sin(np.pi * (x[mask] - zeros[j]) / (zeros[j+1] - zeros[j]))
        elif shape == "double_peak":
            # 双峰：0→peak→0→peak→0
            y = np.zeros_like(x)
            if len(zeros) >= 3:
                for j in range(len(zeros)-1):
                    mask = (x >= zeros[j]) & (x <= zeros[j+1])
                    y[mask] = peak_y * np.sin(np.pi * (x[mask] - zeros[j]) / (zeros[j+1] - zeros[j]))
            else:
                mid = 0.5
                mask1 = (x >= 0) & (x <= mid)
                y[mask1] = peak_y * np.sin(np.pi * x[mask1] / mid)
                mask2 = (x >= mid) & (x <= 1)
                y[mask2] = peak_y * np.sin(np.pi * (x[mask2] - mid) / (1 - mid))
        else:
            y = peak_y * np.sin(np.pi * x)

        ax.plot(x, y, color=color, lw=2, label=f'({label})')

    ax.legend(fontsize=11)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xticklabels(['0', '', r'$\pi/2$' if title else '0.5', '', r'$\pi$' if title else '1'])
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _render_mixed(title: str, elements: list) -> str:
    # Mixed mode: show geometry + function side by side, or just geometry
    geom_els = [e for e in elements if e.get("kind") in ("circle", "point", "line", "right_angle", "angle")]
    func_els = [e for e in elements if e.get("kind") == "curve"]

    if not func_els:
        return _render_geometry(title, geom_els)
    if not geom_els:
        return _render_functions(title, func_els)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # 几何图
    points = {}
    xs, ys = [], []
    for el in geom_els:
        if el.get("kind") == "point":
            points[el.get("label","")] = (float(el.get("x",0)), float(el.get("y",0)))
            xs.append(float(el.get("x",0))); ys.append(float(el.get("y",0)))
        elif el.get("kind") == "circle":
            cx, cy, r = float(el.get("cx",0)), float(el.get("cy",0)), float(el.get("r",1))
            points[el.get("label","")] = (cx, cy)
            xs.extend([cx-r, cx+r]); ys.extend([cy-r, cy+r])
    if not xs: xs, ys = [-1.5,1.5], [-1.5,1.5]

    marg = 0.5
    ax1.set_aspect('equal')
    ax1.grid(True, alpha=0.2)
    ax1.set_xlim(min(xs)-marg, max(xs)+marg)
    ax1.set_ylim(min(ys)-marg, max(ys)+marg)

    for el in geom_els:
        if el.get("kind") == "circle":
            cx, cy, r = float(el.get("cx",0)), float(el.get("cy",0)), float(el.get("r",1))
            ax1.plot(cx + r*np.cos(np.linspace(0,2*np.pi,300)), cy + r*np.sin(np.linspace(0,2*np.pi,300)), 'k-', lw=1.5)
        elif el.get("kind") == "line":
            a, b = points.get(el.get("from","")), points.get(el.get("to",""))
            if a and b:
                ls = "--" if el.get("style") == "dashed" else "-"
                ax1.plot([a[0],b[0]], [a[1],b[1]], el.get("color","b"), ls=ls, lw=1.5)
        elif el.get("kind") == "right_angle":
            at = points.get(el.get("at",""))
            if at:
                s = 0.08
                ax1.plot([at[0],at[0]+s],[at[1],at[1]],'k-',lw=1)
                ax1.plot([at[0],at[0]],[at[1],at[1]+s],'k-',lw=1)
        elif el.get("kind") == "angle":
            at = points.get(el.get("at",""))
            fr = points.get(el.get("from",""))
            to = points.get(el.get("to",""))
            if at and fr and to:
                a1 = np.arctan2(fr[1]-at[1], fr[0]-at[0])
                a2 = np.arctan2(to[1]-at[1], to[0]-at[0])
                if a2 < a1: a2 += 2*np.pi
                r = 0.25
                t = np.linspace(a1, a2, 40)
                ax1.plot(at[0]+r*np.cos(t), at[1]+r*np.sin(t), 'k-', lw=1.2)
                mid = (a1+a2)/2
                ax1.text(at[0]+r*1.3*np.cos(mid), at[1]+r*1.3*np.sin(mid), f'${el.get("label","")}$', fontsize=13)

    for name, (x, y) in points.items():
        ax1.plot(x, y, 'ko', ms=5, zorder=5)
        ax1.text(x+0.04, y+0.04, f'${name}$', fontsize=12)
    ax1.set_title('Geometry', fontsize=13, fontweight='bold')

    # 函数图
    ax2.grid(True, alpha=0.2)
    ax2.set_xlim(-0.05, 1.05)
    ax2.set_ylim(-0.05, 1.15)
    colors = ['blue', 'green', 'orange', 'red']
    for i, el in enumerate(func_els):
        shape = el.get("shape", "single_peak")
        peak_y = float(el.get("peak_y", 1))
        zeros = [float(z) for z in el.get("zeros", [0, 1])]
        label = el.get("label", f"Option {i+1}")

        x = np.linspace(0, 1, 300)
        y = np.zeros_like(x)
        for j in range(len(zeros)-1):
            mask = (x >= zeros[j]) & (x <= zeros[j+1])
            if shape == "double_peak" and len(zeros) >= 3:
                y[mask] = peak_y * np.sin(np.pi * (x[mask]-zeros[j])/(zeros[j+1]-zeros[j]))
            elif shape == "single_peak":
                y[mask] = peak_y * np.sin(np.pi * (x[mask]-zeros[j])/(zeros[j+1]-zeros[j]))
        ax2.plot(x, y, color=colors[i%4], lw=2, label=f'({label})')

    ax2.legend(fontsize=11)
    ax2.set_title('Options', fontsize=13, fontweight='bold')

    if title:
        fig.suptitle(title, fontsize=15, fontweight='bold')
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()
