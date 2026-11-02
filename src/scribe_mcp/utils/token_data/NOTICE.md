# Third-party tokenizer resource notices

This directory currently contains four of the six raw resources used by the
seven tiktoken 0.14.0 encoding recipes. The GPT-2 resources `vocab.bpe` and
`encoder.json` are not present. This is a partial resource acquisition record;
it makes no claim about runtime integration, distribution contents, token
parity, offline operation or startup performance.

## Immutable upstream identity and expected-hash source

tiktoken release: **0.14.0**. Source commit:
`4e71bbe0c078468e00fefbf94b39849389f346e5`.

The expected SHA256 values below were fixed independently of the downloaded
responses using the `expected_hash` literals in the pinned
[openai_public.py](https://github.com/openai/tiktoken/blob/4e71bbe0c078468e00fefbf94b39849389f346e5/tiktoken_ext/openai_public.py).
The recipes in that file also define each resource's consumers. This notice
records provenance; it is not a source of runtime hash constants.

## Acquired resources

Each origin URL below is also its observed effective URL. Each file was fetched
once with curl **8.5.0**, libcurl **8.5.0**, OpenSSL **3.0.13**, using system TLS
verification. All four responses were **HTTP 200**, with **zero redirects** and
curl `ssl_verify_result=0`. No proxy override, custom trust store or insecure
option was introduced. UTC acquisition times are the completed download files'
filesystem modification times, measured before copying.

| File | Exact origin and effective URL | Acquired UTC | Raw bytes | Response Content-Length | Consuming recipes |
| --- | --- | --- | ---: | ---: | --- |
| r50k_base.tiktoken | https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken | 2026-11-02T01:51:37.926664Z | 835554 | 835554 | r50k_base |
| p50k_base.tiktoken | https://openaipublic.blob.core.windows.net/encodings/p50k_base.tiktoken | 2026-11-02T01:51:48.630605Z | 836186 | 836186 | p50k_base, p50k_edit |
| cl100k_base.tiktoken | https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken | 2026-11-02T01:51:58.412111Z | 1681126 | 1681126 | cl100k_base |
| o200k_base.tiktoken | https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken | 2026-11-02T01:52:09.982496Z | 3613922 | 3613922 | o200k_base, o200k_harmony |

| File | Independently expected SHA256 | Observed SHA256 before and after binary copy |
| --- | --- | --- |
| r50k_base.tiktoken | 306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930 | 306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930 |
| p50k_base.tiktoken | 94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069 | 94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069 |
| cl100k_base.tiktoken | 223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7 | 223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7 |
| o200k_base.tiktoken | 446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d | 446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d |

All four files are strict ASCII rank text, with LF line endings, a final LF,
no header and no blank lines. Strict base64 decoding, nonempty decoded tokens,
ASCII decimal ranks and unique decoded tokens and ranks were checked without
using a tokenizer loader or engine. Total raw resource bytes: **6966788**.

| File | Rank count / line count | Minimum rank | Maximum rank |
| --- | ---: | ---: | ---: |
| r50k_base.tiktoken | 50256 | 0 | 50255 |
| p50k_base.tiktoken | 50280 | 0 | 50280 |
| cl100k_base.tiktoken | 100256 | 0 | 100255 |
| o200k_base.tiktoken | 199998 | 0 | 199997 |

Acquisition method: a fresh empty private directory outside the source tree;
exact HTTPS origin; curl with `-q --proto '=https' --proto-redir '=https'
--max-redirs 0 --connect-timeout 15 --max-time 60 --max-filesize 10000000
--fail --silent --show-error`, with response headers and metadata recorded.
There was no `-L`, retry, alternate origin, tokenizer constructor, upstream
loader or host-cache substitution. Response status, Content-Length versus
actual bytes, and the independently fixed SHA256 were checked before binary
copying. All four deliberately wrong expected-hash dry checks rejected the
already verified bytes without another fetch. Production binary Git attributes
were established before copying; the resource bytes were not normalized.

## Per-file license basis

The complete pinned tiktoken MIT license appears below. In
[upstream issue 92](https://github.com/openai/tiktoken/issues/92), collaborator
hauntsaninja clarified on 2023-04-05 that the repository license applies to the
encoding files. That issue explicitly names r50k_base, p50k_base, p50k_edit and
cl100k_base (as well as GPT-2), including externally hosted files.

| Acquired file | Redistribution basis |
| --- | --- |
| r50k_base.tiktoken | Pinned tiktoken MIT license and issue-92 encoding-file clarification; explicitly named encoding. |
| p50k_base.tiktoken | Pinned tiktoken MIT license and issue-92 clarification; both consuming p50k recipes were explicitly named. |
| cl100k_base.tiktoken | Pinned tiktoken MIT license and issue-92 clarification; explicitly named encoding. |
| o200k_base.tiktoken | Pinned tiktoken MIT license and the general encoding-file clarification, applied to this later file as an accepted scope inference. o200k was not named in the 2023 issue; this is not a separate explicit o200k-specific upstream grant. |

The future GPT-2 pair requires its own acquisition record and the full original
GPT-2 Modified MIT notice in addition to the tiktoken MIT notice. Neither GPT-2
file has been acquired into this directory at this stage.

## Full tiktoken MIT license

Source: [LICENSE at the pinned commit](https://github.com/openai/tiktoken/blob/4e71bbe0c078468e00fefbf94b39849389f346e5/LICENSE).

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
