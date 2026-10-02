---
name: 古法作业.skill
description: 用一次性结构化答案和短 prompt 生成仿真手写作业 PDF，减少重复上下文和 imagegen 输出浪费。
---

# 古法作业.skill

这个版本保留原 skill 的隔离 job、imagegen、PDF 打包和校验流程，但把解题结果与题目文本分开：代理先生成一次 answers.json，后续每页只发送当前页答案。

## 流程

1. 为每个源文件建立 job_id 目录，复制为 source.<ext>。
2. 代理先完整解题并写出结构化 answers.json：

~~~json
{
  "pages": [
    {
      "question_scope": "1-4",
      "answer_text": "1. ...\n2. ...",
      "source_page": 1,
      "assumptions": []
    }
  ]
}
~~~

3. 运行 scripts/prepare_lite.py。它只把当前页的 answer_text 写进 prompt，不重复嵌入完整题目。
4. 对 manifest 中每页调用一次内置 imagegen，并附上题目视觉页和笔迹样例。
5. 将返回 PNG 保存到 manifest 的 target_png。只打印输出路径或 output_hint，绝不打印完整结果或 Base64。
6. 运行 scripts/package_outputs.py，再运行 scripts/validate_job.py。

## 减少额度的约束

- 不再单独调用分页规划 prompt；分页由代理在生成 answers.json 时决定。
- 不把完整 source_text.txt 拼入每页 prompt。
- handwriting prompt 保持短且稳定。
- imagegen 只负责视觉呈现，不重新计算或改写答案。
- 如果 imagegen 不接受 PDF，先准备 visual-dir，其中放 page001.png、page002.jpg 等页面图。

## 命令

~~~powershell
python scripts/prepare_lite.py --input-file D:\path\homework.pdf --answers D:\path\answers.json --sample-image .\handwriting-example.jpg --visual-dir D:\path\visual-pages

python scripts/package_outputs.py --job-dir D:\path\homework --job-id homework
python scripts/validate_job.py --job-dir D:\path\homework --job-id homework
~~~

不要在 pages 中手工放入答案图片；只有真实 imagegen 输出才能进入最终 PDF。
