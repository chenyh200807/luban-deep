# t5_wrong — FAIL
- title: MCQ(qid=8731)·答错(选D河砂)
- turn_id: 
- turn_status: driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}

## 断言
- A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
- A5 **PASS** — 无罐头拒答用语
- M1 **FAIL** — contains_all['外加剂'] 缺 ['外加剂']
- M2 **FAIL** — contains_any['不正确', '不对', '错误', '误选', '不是', '并非'] 命中 []
- L1 **FAIL** — len=0 (>=60)

## result 事件 metadata(远端只读摘取)
```json
null
```

## 发送的题面/作答
```
混凝土材料进场复试中，对有氯离子含量要求时，首先需要检验氯化物含量的是（　　）。
A. 粉煤灰
B. 外加剂
C. 碎石
D. 河砂

我选D（河砂），因为河砂用量最大，氯离子总量贡献最大。对吗？
```

## 完整回复
```

```
