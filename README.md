# 钱斌治课题组中文主页原型

这是一个 GitHub Pages 友好的中文静态网站原型，当前不依赖构建工具。站点已改为多页面结构。

## 页面结构

- `index.html`：首页
- `pi.html`：PI 简介
- `platforms.html`：技术平台
- `publications.html`：代表论文
- `members.html`：团队成员
- `contact.html`：联系与加入我们

## 本地预览

直接用浏览器打开 `index.html` 即可。

也可以在本目录运行：

```bash
python -m http.server 8000
```

然后访问：

```text
http://localhost:8000
```

## 发布到 GitHub Pages

若使用用户主页形式，GitHub 仓库名必须为：

```text
<GitHub用户名>.github.io
```

发布网址为：

```text
https://<GitHub用户名>.github.io/
```

仓库的 `Settings → Pages → Build and deployment → Source` 需选择 `GitHub Actions`。推送到 `main` 分支后，`.github/workflows/deploy-pages.yml` 会发布网页成品。

## 后续需要补充的素材

- 团队成员姓名
- 成员照片
- 成员邮箱
- 成员研究方向
- 更完整的论文列表及 DOI 链接
- 可公开展示的空间组学/实验平台图片

## 更新团队成员

团队成员数据以 `课题组成员/照片以及个人简介收集_已排序.xlsx` 为唯一来源。请按 Excel 行顺序维护成员；PI 固定显示在首位。必填列为“姓名”“照片文件名”“个人简介”，可选列为“职称/身份（可选）”“邮箱（可选）”。照片文件需放在 `课题组成员/`，且文件名必须与 Excel 完全一致。

修改 Excel 或新增照片后，在网站根目录运行：

```bash
python scripts/update_members.py
```

该命令会更新 `members.html`，并复制本次 Excel 中引用的照片到 `assets/members/`；不会删除原始照片。执行后需提交更新的 `members.html` 与 `assets/members/`。

`课题组成员/` 和 `assets/pi_en.docx` 属于本地源材料，已通过 `.gitignore` 排除，不会进入公开仓库。GitHub Actions 只打包网页、样式、脚本和网页实际使用的图片。
