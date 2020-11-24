"""
This module defines a pandoc filter for manubot cite functionality.

Related development commands:

```shell
# export to plain text
pandoc \
  --to=plain \
  --standalone \
  --bibliography=manubot/pandoc/tests/test_cite_filter/bibliography.json \
  --bibliography=manubot/pandoc/tests/test_cite_filter/bibliography.bib \
  --filter=pandoc-manubot-cite \
  --filter=pandoc-citeproc \
  manubot/pandoc/tests/test_cite_filter/input.md

# call the filter manually using pandoc JSON output
pandoc \
  --to=json \
  manubot/pandoc/tests/test_cite_filter/input.md \
  | python manubot/pandoc/test_cite.py markdown
```

Related resources on pandoc filters:

- [python pandocfilters package](https://github.com/jgm/pandocfilters)
- [python panflute package](https://github.com/sergiocorreia/panflute)
- [panflute Citation class](http://scorreia.com/software/panflute/code.html#panflute.elements.Citation)
"""
import argparse
import logging
import os
from typing import Any, Dict

import panflute as pf

from manubot.cite.citations import Citations


def parse_args() -> argparse.Namespace:
    """
    Read command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Pandoc filter for citation by persistent identifier. "
        "Filters are command-line programs that read and write a JSON-encoded abstract syntax tree for Pandoc. "
        "Unless you are debugging, run this filter as part of a pandoc command by specifying --filter=pandoc-manubot-cite."
    )
    parser.add_argument(
        "target_format",
        help="output format of the pandoc command, as per Pandoc's --to option",
    )
    parser.add_argument(
        "--input",
        nargs="?",
        type=argparse.FileType("r", encoding="utf-8"),
        help="path read JSON input (defaults to stdin)",
    )
    parser.add_argument(
        "--output",
        nargs="?",
        type=argparse.FileType("w", encoding="utf-8"),
        help="path to write JSON output (defaults to stdout)",
    )
    args = parser.parse_args()
    return args


def _get_citekeys_action(elem: pf.Element, doc: pf.Doc) -> None:
    """
    Panflute action to extract citationId from all Citations in the AST.
    """
    if not isinstance(elem, pf.Citation):
        return None
    manuscript_citekeys = doc.manubot["manuscript_citekeys"]
    manuscript_citekeys.append(elem.id)
    return None


def _citation_to_id_action(elem: pf.Element, doc: pf.Doc) -> None:
    """
    Panflute action to update the citationId of Citations in the AST
    with their manubot-created keys.
    """
    if not isinstance(elem, pf.Citation):
        return None
    mapper = doc.manubot["citekey_shortener"]
    if elem.id in mapper:
        elem.id = mapper[elem.id]
    return None


def _get_reference_link_citekey_aliases(elem: pf.Element, doc: pf.Doc) -> None:
    """
    Extract citekey aliases from the document that were defined
    using markdown's link reference syntax.
    https://spec.commonmark.org/0.29/#link-reference-definitions

    Based on pandoc-url2cite implementation by phiresky at
    https://github.com/phiresky/pandoc-url2cite/blob/b28374a9a037a5ce1747b8567160d8dffd64177e/index.ts#L118-L152
    """
    if type(elem) != pf.Para:
        # require link reference definitions to be in their own paragraph
        return
    while (
        len(elem.content) >= 3
        and type(elem.content[0]) == pf.Cite
        and len(elem.content[0].citations) == 1
        and type(elem.content[1]) == pf.Str
        and elem.content[1].text == ":"
    ):
        # paragraph consists of at least a Cite (with one Citation),
        # a Str (equal to ":"), and additional elements, such as a
        # link destination and possibly more link-reference definitions.
        space_index = 3 if type(elem.content[2]) == pf.Space else 2
        destination = elem.content[space_index]
        if type(destination) == pf.Str:
            # paragraph starts with `[@something]: something`
            # save info to citekeys and remove from paragraph
            citekey = elem.content[0].citations[0].id
            citekey_aliases = doc.manubot["citekey_aliases"]
            if (
                citekey in citekey_aliases
                and citekey_aliases[citekey] != destination.text
            ):
                logging.warning(f"multiple aliases defined for @{citekey}")
            citekey_aliases[citekey] = destination.text
            # found citation, add it to citekeys and remove it from document
            elem.content = elem.content[space_index + 1 :]
        # remove leading SoftBreak, before continuing
        if len(elem.content) > 0 and type(elem.content[0]) == pf.SoftBreak:
            elem.content.pop(0)


def _get_load_manual_references_kwargs(doc: pf.Doc) -> Dict[str, Any]:
    """
    Return keyword arguments for Citations.load_manual_references.
    """
    manual_refs = doc.get_metadata("references", default=[])
    bibliography_paths = doc.get_metadata("bibliography", default=[])
    if not isinstance(bibliography_paths, list):
        bibliography_paths = [bibliography_paths]
    bibliography_cache_path = doc.manubot["bibliography_cache"]
    if (
        bibliography_cache_path
        and bibliography_cache_path not in bibliography_paths
        and os.path.exists(bibliography_cache_path)
    ):
        bibliography_paths.append(bibliography_cache_path)
    return dict(
        paths=bibliography_paths,
        extra_csl_items=manual_refs,
    )


def process_citations(doc: pf.Doc) -> None:
    """
    Apply citation-by-identifier to a Python object representation of
    Pandoc's Abstract Syntax Tree.

    The following Pandoc metadata fields are considered:

    - bibliography (use to define reference metadata manually)
    - citekey-aliases (use to define tags for cite-by-id citations)
    - manubot-bibliography-cache:
      Path to read and write bibliographic metadata as CSL JSON.
      Intended as a human-editable cache of the bibliography data,
      for situations where this filter is run multiple times.
    - manubot-requests-cache-path
    - manubot-clear-requests-cache
    - manubot-output-citekeys: path to write TSV table of citekeys
    - manubot-output-bibliography: path to write generated CSL JSON bibliography
    """
    # process metadata.manubot-bibliography-cache
    bib_cache = doc.get_metadata(key="manubot-bibliography-cache")
    if not (bib_cache is None or isinstance(bib_cache, str)):
        logging.warning(
            f"Expected metadata.manubot-bibliography-cache to be a string or null (None), "
            f"but received a {bib_cache.__class__.__name__}. Setting to None."
        )
        bib_cache = None
    doc.manubot["bibliography_cache"] = bib_cache
    # process metadata.citekey-aliases
    citekey_aliases = doc.get_metadata("citekey-aliases", default={})
    if not isinstance(citekey_aliases, dict):
        logging.warning(
            f"Expected metadata.citekey-aliases to be a dict, "
            f"but received a {citekey_aliases.__class__.__name__}. Disregarding."
        )
        citekey_aliases = dict()
    doc.manubot["citekey_aliases"] = citekey_aliases
    doc.walk(_get_reference_link_citekey_aliases)
    doc.walk(_get_citekeys_action)
    manuscript_citekeys = doc.manubot["manuscript_citekeys"]
    citations = Citations(input_ids=manuscript_citekeys, aliases=citekey_aliases)
    citations.csl_item_failure_log_level = "ERROR"

    requests_cache_path = doc.get_metadata("manubot-requests-cache-path")
    if requests_cache_path:
        from manubot.process.requests_cache import RequestsCache

        req_cache = RequestsCache(requests_cache_path)
        req_cache.mkdir()
        req_cache.install()
        if doc.get_metadata("manubot-clear-requests-cache", default=False):
            req_cache.clear()

    citations.filter_pandoc_xnos()
    citations.load_manual_references(**_get_load_manual_references_kwargs(doc))
    citations.inspect(log_level="WARNING")
    citations.get_csl_items()
    doc.manubot["citekey_shortener"] = citations.input_to_csl_id
    doc.walk(_citation_to_id_action)

    if requests_cache_path:
        req_cache.close()

    citations.write_citekeys_tsv(path=doc.get_metadata("manubot-output-citekeys"))
    citations.write_csl_json(path=doc.get_metadata("manubot-output-bibliography"))
    citations.write_csl_json(path=doc.manubot["bibliography_cache"])
    # Update pandoc metadata with fields that this filter
    # has either consumed, created, or modified.
    doc.metadata["bibliography"] = []
    doc.metadata["references"] = citations.csl_items
    doc.metadata["citekey_aliases"] = citekey_aliases


def main() -> None:
    from manubot.command import setup_logging_and_errors, exit_if_error_handler_fired

    diagnostics = setup_logging_and_errors()
    args = parse_args()
    # Let panflute handle io to sys.stdout / sys.stdin to set utf-8 encoding.
    # args.input=None for stdin, args.output=None for stdout
    doc = pf.load(input_stream=args.input)
    log_level = doc.get_metadata("manubot-log-level", "WARNING")
    diagnostics["logger"].setLevel(getattr(logging, log_level))
    doc.manubot = {"manuscript_citekeys": []}
    process_citations(doc)
    pf.dump(doc, output_stream=args.output)
    if doc.get_metadata("manubot-fail-on-errors", False):
        exit_if_error_handler_fired(diagnostics["error_handler"])


if __name__ == "__main__":
    main()
