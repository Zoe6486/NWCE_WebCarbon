import os
import argparse
import cssutils
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_huggingface import HuggingFacePipeline

MAX_TOKENS_PER_CHUNK = 1800


def extract_css_blocks(css_text):
    cssutils.log.setLevel('FATAL')
    sheet = cssutils.parseString(css_text, validate=False)
    blocks = []
    for rule in sheet:
        if rule.type == rule.STYLE_RULE:
            block_text = str(rule.cssText)
            blocks.append(block_text)
    return blocks


def group_blocks_by_token_limit(blocks, tokenizer, max_tokens):
    chunks = []
    current_chunk = ""
    current_tokens = 0

    for block in blocks:
        block_tokens = len(tokenizer.encode(block))
        if current_tokens + block_tokens > max_tokens:
            chunks.append(current_chunk.strip())
            current_chunk = block
            current_tokens = block_tokens
        else:
            current_chunk += "\n\n" + block
            current_tokens += block_tokens

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def run_llm_safe(project_name):
    group = "llm"
    input_path = os.path.join("css_optimizer", "css_original", project_name, "style.css")
    output_dir = os.path.join("css_optimizer", "css_optimized", project_name, group)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "style.css")

    if not os.path.exists(input_path):
        print(f"❌ 找不到输入文件: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        css_code = f.read()

    model_name = "deepseek-ai/deepseek-coder-6.7b-instruct"
    print("🧠 正在加载 DeepSeek 模型...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name, device_map="auto", torch_dtype="auto")
    except Exception as e:
        print("❌ 模型加载失败:", e)
        return

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=1024,
        do_sample=False,
        return_full_text=False,
    )
    llm = HuggingFacePipeline(pipeline=pipe)

    # ✅ 高质量 Prompt（避免瞎删/重排）
    prompt_template = PromptTemplate(
        input_variables=["css_code"],
        template=(
            "你是一个前端性能优化专家。请优化以下 CSS 代码，目标：\n"
            "- 删除无效或重复样式\n"
            "- 合并重复声明\n"
            "- 保持视觉一致性和语义一致性\n"
            "- 不更改选择器名称、顺序或嵌套结构\n"
            "- 不删除任何规则，除非与其他规则完全重复\n"
            "- 不将样式压缩成一行，保留格式可读性\n\n"
            "{css_code}"
        )
    )

    chain: RunnableSequence = prompt_template | llm

    blocks = extract_css_blocks(css_code)
    chunks = group_blocks_by_token_limit(blocks, tokenizer, MAX_TOKENS_PER_CHUNK)

    print(f"🔍 发现 {len(blocks)} 个 CSS 规则块，分为 {len(chunks)} 个 LLM 输入块")

    optimized_css_chunks = []

    for i, chunk in enumerate(chunks):
        print(f"🧩 正在优化第 {i+1}/{len(chunks)} 块...")
        print(f"   ⤷ chunk 字符数: {len(chunk)}, token 数: {len(tokenizer.encode(chunk))}")
        try:
            result = chain.invoke({"css_code": chunk})
            optimized_css_chunks.append(result.strip())
        except Exception as e:
            print(f"❌ 第 {i+1} 块优化失败:", e)

    final_css = "\n\n".join(optimized_css_chunks)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_css)

    print(f"📊 优化前行数: {len(css_code.splitlines())}")
    print(f"📊 优化后行数: {len(final_css.splitlines())}")
    print(f"✅ 所有块优化完成，结果保存到：{output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="结构安全的 LLM CSS 优化（防止瞎删 + 打印分析）")
    parser.add_argument("project_name", help="项目名（如 site3）")
    args = parser.parse_args()

    run_llm_safe(args.project_name)

