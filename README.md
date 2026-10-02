# 古法作业 Lite

这是原 Hand-crafted-Homework.skill 的低额度变体。

改动重点：

- 代理只解题一次，并写入 answers.json。
- 每页 prompt 只包含当前页答案，不重复完整题目文本。
- imagegen 只负责手写视觉呈现，不重新计算答案。
- imagegen 返回值只处理路径元数据，禁止打印 PNG Base64。
- 继续复用原来的 PNG→PDF 打包和 job 校验脚本。

基本命令：

~~~powershell
python scripts/prepare_lite.py --input-file D:\path\homework.pdf --answers D:\path\answers.json --sample-image .\handwriting-example.jpg --visual-dir D:\path\visual-pages
python scripts/package_outputs.py --job-dir D:\path\homework --job-id homework
python scripts/validate_job.py --job-dir D:\path\homework --job-id homework
~~~
