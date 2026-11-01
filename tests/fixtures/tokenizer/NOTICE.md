# Third-party tokenizer test fixture

`cl100k_base.tiktoken` is authentic OpenAI tiktoken test data, used only to
exercise genuine native encoder initialization and retry recovery. It is not a
production resource or a claim of offline tokenizer provisioning. It belongs in
the source distribution's tests, not the runtime wheel.

- Official origin: https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
- Upstream: https://github.com/openai/tiktoken/tree/4e71bbe0c078468e00fefbf94b39849389f346e5
- Pinned expected hash source: https://github.com/openai/tiktoken/blob/4e71bbe0c078468e00fefbf94b39849389f346e5/tiktoken_ext/openai_public.py
- Size: 1,681,126 bytes
- SHA-256: `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`
- Retained on 2026-11-01, byte-for-byte from the locally preprovisioned cache
  `/tmp/data-gym-cache/9b5ad71b2ce5302211f9c61530b329a4922fc6a4`, after verifying
  size and SHA-256. The original cache acquisition time and method are unknown.
- Encoding-file license clarification: https://github.com/openai/tiktoken/issues/92
- License text below: https://raw.githubusercontent.com/openai/tiktoken/4e71bbe0c078468e00fefbf94b39849389f346e5/LICENSE

This third-party data retains its upstream MIT license; it is not relicensed
under Scribe's community license.

```text
MIT License

Copyright (c) 2022 OpenAI, Shantanu Jain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```
