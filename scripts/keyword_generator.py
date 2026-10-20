#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wake word automatic generation tool.

Function:
1. Input Chinese and automatically convert it to pinyin with tones
2. Separate pinyin by letters (initial consonants and finals)
3. Verify whether the token is in tokens.txt
4. Automatically generate keywords.txt format
"""

import sys
from pathlib import Path

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:
    print("❌ 缺少依赖: pypinyin")
    print("请安装: pip install pypinyin")
    sys.exit(1)


class KeywordGenerator:
    def __init__(self, model_dir: Path):
        """Initialize wake word generator.

        Args:
            model_dir: model directory path (including tokens.txt and keywords.txt)
        """
        self.model_dir = Path(model_dir)
        self.tokens_file = self.model_dir / "tokens.txt"
        self.keywords_file = self.model_dir / "keywords.txt"

        # Load existing tokens
        self.available_tokens = self._load_tokens()

        # Initial consonant table (required Separated)
        self.initials = [
            "b",
            "p",
            "m",
            "f",
            "d",
            "t",
            "n",
            "l",
            "g",
            "k",
            "h",
            "j",
            "q",
            "x",
            "zh",
            "ch",
            "sh",
            "r",
            "z",
            "c",
            "s",
            "y",
            "w",
        ]

    def _load_tokens(self) -> set:
        """
        Load all available tokens in tokens.txt.
        """
        if not self.tokens_file.exists():
            print(f"⚠️  Warning: tokens file does not exist: {self.tokens_file}")
            return set()

        tokens = set()
        with open(self.tokens_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Format: "token id" or "token"
                    parts = line.split()
                    if parts:
                        tokens.add(parts[0])

        print(f"✅ 加载了 {len(tokens)} 个可用tokens")
        return tokens

    def _split_pinyin(self, pinyin: str) -> list:
        """Separate Pinyin according to initials and finals.

        For example: "xiǎo" -> ["x", "iǎo"] "mǐ" -> ["m", "ǐ"] "ài" -> ["ài"] (zero initial consonant)
        """
        if not pinyin:
            return []

        # Try to match initial consonants (zh, ch, sh priority)
        for initial in sorted(self.initials, key=len, reverse=True):
            if pinyin.startswith(initial):
                final = pinyin[len(initial) :]
                if final:
                    return [initial, final]
                else:
                    return [initial]

        # No initial consonant (zero initial consonant)
        return [pinyin]

    def chinese_to_keyword_format(self, chinese_text: str) -> str:
        """Convert Chinese to keyword format.

        Args:
            chinese_text: Chinese text, such as "Xiaomi Xiaomi"

        Returns:
            keyword format, such as "x iǎo m ǐ x iǎo m ǐ @小米小米"
        """
        # Convert to tonal Pinyin
        pinyin_list = lazy_pinyin(chinese_text, style=Style.TONE)

        # Split each pinyin
        split_parts = []
        missing_tokens = []

        for pinyin in pinyin_list:
            parts = self._split_pinyin(pinyin)

            # Verify whether each part is in tokens
            for part in parts:
                if part not in self.available_tokens:
                    missing_tokens.append(part)
                split_parts.append(part)

        # Splicing results
        pinyin_str = " ".join(split_parts)
        keyword_line = f"{pinyin_str} @{chinese_text}"

        # If there is a missing token, give a warning
        if missing_tokens:
            print(
                f"⚠️  Warning: these tokens are missing from tokens.txt: {', '.join(set(missing_tokens))}"
            )
            print("   The generated keywords may not work correctly")

        return keyword_line

    def add_keyword(self, chinese_text: str, append: bool = True) -> bool:
        """Add wake word to keywords.tx t.

        Args:
            chinese_text: Chinese wake-up word
            append: whether to append (True) or overwrite (False)

        Returns:
            Whether it is successful
        """
        try:
            # generates keyword format
            keyword_line = self.chinese_to_keyword_format(chinese_text)

            # Check if it already exists
            if self.keywords_file.exists():
                with open(self.keywords_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if f"@{chinese_text}" in content:
                        print(f"⚠️  Keyword '{chinese_text}' already exists")
                        return False

            # Write to file
            mode = "a" if append else "w"
            with open(self.keywords_file, mode, encoding="utf-8") as f:
                f.write(keyword_line + "\n")

            print(f"✅ 成功添加: {keyword_line}")
            return True

        except Exception as e:
            print(f"❌ 添加失败: {e}")
            return False

    def batch_add_keywords(self, chinese_texts: list, overwrite: bool = False):
        """Add wake words in batches.

        Args:
            chinese_texts: Chinese list
            overwrite: Whether to overwrite the original file
        """
        if overwrite:
            print("⚠️  Existing keywords.txt will be overwritten")

        success_count = 0
        for text in chinese_texts:
            text = text.strip()
            if not text:
                continue

            if self.add_keyword(text, append=not overwrite):
                success_count += 1

            # appended after the first one
            overwrite = False

        print(f"\n📊 完成: 成功添加 {success_count}/{len(chinese_texts)} 个关键词")

    def list_keywords(self):
        """
        List all current keywords.
        """
        if not self.keywords_file.exists():
            print("⚠️  keywords.txt does not exist")
            return

        print(f"\n📄 当前关键词列表 ({self.keywords_file}):")
        print("-" * 60)

        with open(self.keywords_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract the Chinese part and display
                    if "@" in line:
                        pinyin_part, chinese_part = line.split("@", 1)
                        print(
                            f"{i}. {chinese_part.strip():15s} -> {pinyin_part.strip()}"
                        )
                    else:
                        print(f"{i}. {line}")

        print("-" * 60)


def main():
    """
    main function.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="唤醒词自动生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 添加单个关键词
  python keyword_generator.py -a "小米小米"

  # 批量添加关键词
  python keyword_generator.py -b "小米小米" "你好小智" "贾维斯"

  # 从文件批量导入（每行一个中文）
  python keyword_generator.py -f keywords_input.txt

  # 列出当前关键词
  python keyword_generator.py -l

  # 测试转换（不写入文件）
  python keyword_generator.py -t "小米小米"
        """,
    )

    parser.add_argument(
        "-m", "--model-dir", default="models", help="模型目录路径（默认: models）"
    )

    parser.add_argument("-a", "--add", help="添加单个关键词（中文）")

    parser.add_argument(
        "-b", "--batch", nargs="+", help="批量添加关键词（多个中文，空格分隔）"
    )

    parser.add_argument("-f", "--file", help="从文件批量导入（每行一个中文）")

    parser.add_argument("-l", "--list", action="store_true", help="列出当前所有关键词")

    parser.add_argument("-t", "--test", help="测试转换（不写入文件）")

    parser.add_argument(
        "--overwrite", action="store_true", help="覆盖模式（清空现有关键词）"
    )

    args = parser.parse_args()

    # to determine the model directory
    if Path(args.model_dir).is_absolute():
        model_dir = Path(args.model_dir)
    else:
        # relative path: relative to the project root directory
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        model_dir = project_root / args.model_dir

    if not model_dir.exists():
        print(f"❌ 模型目录不存在: {model_dir}")
        sys.exit(1)

    print(f"🔧 使用模型目录: {model_dir}")

    # Create generator
    generator = KeywordGenerator(model_dir)

    # Perform the operation
    if args.test:
        # Test mode
        print("\n🧪 Test conversion:")
        keyword_line = generator.chinese_to_keyword_format(args.test)
        print(f"   Input: {args.test}")
        print(f"   Output: {keyword_line}")

    elif args.add:
        # Add a single
        generator.add_keyword(args.add)

    elif args.batch:
        # Add in batches
        generator.batch_add_keywords(args.batch, overwrite=args.overwrite)

    elif args.file:
        # Import from file
        input_file = Path(args.file)
        if not input_file.exists():
            print(f"❌ 文件不存在: {input_file}")
            sys.exit(1)

        with open(input_file, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]

        print(f"📥 从文件导入 {len(keywords)} 个关键词")
        generator.batch_add_keywords(keywords, overwrite=args.overwrite)

    elif args.list:
        # List keywords
        generator.list_keywords()

    else:
        # Interactive mode
        print("\n🎤 唤醒词生成工具（交互模式）")
        print("输入中文唤醒词，按 Ctrl+C 或输入 'q' 退出\n")

        try:
            while True:
                chinese = input("请输入中文唤醒词: ").strip()

                if not chinese or chinese.lower() == "q":
                    break

                generator.add_keyword(chinese)
                print()

        except KeyboardInterrupt:
            print("\n\n👋 已退出")

    # Finally list all keywords
    if not args.list and (args.add or args.batch or args.file):
        generator.list_keywords()


if __name__ == "__main__":
    main()
