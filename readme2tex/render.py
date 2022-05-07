#!/usr/bin/env python
import hashlib
import os
import random
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from subprocess import check_output
from xml.sax.saxutils import quoteattr
import logging

envelope = r'''%% processed with readme2tex
\documentclass{article}
%s
\usepackage{geometry}
\pagestyle{empty}
\geometry{paperwidth=250mm, paperheight=16383pt, left=0pt, top=0pt, textwidth=426pt, marginparsep=20pt, marginparwidth=100pt, textheight=16263pt, footskip=40pt}
\begin{document}
%s%s
\end{document}
'''

try:
    input = raw_input
except NameError:
    pass

def rendertex(engine, string, packages, temp_dir, block):
    if engine != 'latex': raise Exception("Not Implemented")
    source = envelope % ('\n'.join(r'\usepackage{%s}' % ''.join(package) for package in packages), 'a' if not block else '', string)
    name = hashlib.md5(string.encode('utf-8')).hexdigest()
    source_file = os.path.join(temp_dir, name + '.tex')
    with open(source_file, 'w', encoding = 'utf-8') as file:
        file.write(source)

    try:
        check_output(
            [engine, '-output-directory=' + temp_dir, '-interaction', 'nonstopmode', source_file],
            stderr=sys.stdout)
        # compile one more time to address below warning:
        #     LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.
        #
        # -----------------------
        # More background:
        # -----------------------
        # LaTeX will calculate the right numbering for the objects in the document; the marker you have used to label the object will not be shown anywhere in the document. Instead, LaTeX will replace the string "\ref{marker}" with the right number that was assigned to the object. If you reference a marker that does not exist, the compilation of the document will be successful but LaTeX will return a warning:
        # 
        #     LaTeX Warning: There were undefined references.
        # 
        # and it will replace "\ref{unknown-marker}" with "??" — so that it will be easier to find in the document.
        # 
        # As you may have noticed, this way of cross-referencing is a two-step process: first the compiler has to store the labels with the right number to be used for referencing, then it has to replace the \ref with the right number.
        # 
        # Because of that, you would have to compile your document twice to see the output with the proper numbering. If you only compile it once, then LaTeX will use the older information collected in previous compilations (which might be outdated), and the compiler will inform you by printing the following message at the end of the compilation:
        # 
        #     LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.
        #
        # reference:
        #     https://en.wikibooks.org/wiki/LaTeX/Labels_and_Cross-referencing#Introduction
        check_output(
            [engine, '-output-directory=' + temp_dir, '-interaction', 'nonstopmode', source_file],
            stderr=sys.stdout)
    except:
        logging.warning("'%s' has warnings during compilation. See %s/%s", string, temp_dir, name)
    dvi = os.path.join(temp_dir, name + '.dvi')
    svg = check_output(
        ['dvisvgm', '-v0', '-a', '-n', '-s', dvi])
    return svg, dvi, name


def svg2png(svg):
    # assume that 'cairosvg' exists
    import cairosvg
    cairosvg.svg2png(url=svg, write_to=svg[:-4] + '.png', dpi=250)
    return svg[:-4] + '.png'


def extract_equations(content):

    contentInd = 0

    while True:
        if(contentInd >= len(content) - 1):
            break

        # GitHub fenced code block start pattern has 4 parts
        #   part #1: 3 or more backticks characters, --------------------------- it is a match group
        #   part #2: (optional) 0 or more repetitions of whitespace characters
        #   part #3: (optional) lauguage string, ------------------------------- it is a match group
        #   part #4: (optional) 0 or more repetitions of whitespace characters
        githubFencedCodeBlockStartPattern = r'([`]{3,})[ \t]*(\w+)?[ \t]*'

        # LaTeX start pattern has 3 parts
        #   part #1: \begin{
        #   part #2: math environment, ----------------------------------------- it is a match group
        #   part #3: }
        latexMathEnvStartPattern = r'\\begin\{([\w*]+)\}'
        startPattern = r'' + githubFencedCodeBlockStartPattern + '|' + latexMathEnvStartPattern

        startMatch = re.search(startPattern, content[contentInd:])
        if(not startMatch):
            break

        if(startMatch.group(1)):
            # '```' is found, it is inside Github fenced code block

            # +--------------------------------------------------------------------------- 1st search start index, looking for "``` xxx"
            # |              +------------------------------------------------------------ 2nd search start index, looking for "```"
            # |<------------>|<------------------------------------------------------>|
            # |<------------>|<--------------------------------------------->|        |
            # |<------------>|                                               |        |
            # |<->|          |                                               |        |
            # |   |StartMatch|                                               |EndMatch|
            # | start       end                                            start     end
            # +---+----------+-----------------------------------------------+--------+
            #     |          |                                               |        +--- contentInd + startMatch.end() + endMatch.end()
            #     |          |                                               +------------ contentInd + startMatch.end() + endMatch.start()
            #     |          +------------------------------------------------------------ contentInd + startMatch.end()
            #     +----------------------------------------------------------------------- contentInd + startMatch.start()
            backticksStr = startMatch.group(1)
            language     = startMatch.group(2)

            # exactly match "```", "````", "`````"...
            endPattern = r'' + backticksStr
            endMatch = re.search(endPattern, content[contentInd + startMatch.end():])
            if(not endMatch):
                raise ValueError('cannot find ending match for pattern: "' + endPattern + '"')

            if(language and language == "tex"):
                # language is present, and it is also equal to "tex"
                # Display Math mode = True
                yield (content[contentInd + startMatch.end() : contentInd + startMatch.end() + endMatch.start()], 
                       contentInd + startMatch.start(),
                       contentInd + startMatch.end() + endMatch.end(),
                       True)

            contentInd = contentInd + startMatch.end() + endMatch.end()

        else:
            # \begin{xxx} is found, it is LaTeX math environment

            # +--------------------------------------------------------------------------- 1st search start index, looking for "\begin{xxx}"
            # |              +------------------------------------------------------------ 2nd search start index, looking for "\end{xxx}"
            # |<------------>|<------------------------------------------------------>|
            # |<------------>|<--------------------------------------------->|        |
            # |<------------>|                                               |        |
            # |<->|          |                                               |        |
            # |   |StartMatch|                                               |EndMatch|
            # | start       end                                            start     end
            # +---+----------+-----------------------------------------------+--------+
            #     |          |                                               |        +--- contentInd + startMatch.end() + endMatch.end()
            #     |          |                                               +------------ contentInd + startMatch.end() + endMatch.start()
            #     |          +------------------------------------------------------------ contentInd + startMatch.end()
            #     +----------------------------------------------------------------------- contentInd + startMatch.start()
            mathEnv = startMatch.group(3)

            endPattern = r'\\end\{' + re.escape(mathEnv) + '\}'
            
            endMatch = re.search(endPattern, content[contentInd + startMatch.end():])
            if(not endMatch):
                raise ValueError('cannot find ending match for pattern: "' + endPattern + '"')
            
            if(mathEnv == 'math'):
                # it is Inline Math mode
                # Display Math mode = False
                yield (content[contentInd + startMatch.start() : contentInd + startMatch.end() + endMatch.end()], 
                       contentInd + startMatch.start(),
                       contentInd + startMatch.end() + endMatch.end(),
                       False)
            else:
                # Display Math mode = True
                yield (content[contentInd + startMatch.start() : contentInd + startMatch.end() + endMatch.end()], 
                       contentInd + startMatch.start(),
                       contentInd + startMatch.end() + endMatch.end(),
                       True)

            contentInd = contentInd + startMatch.end() + endMatch.end()



def render(
        readme,
        output='README_GH.md',
        engine='latex',
        packages=('amsmath', 'amssymb'),
        svgdir='svgs',
        branch=None,
        user=None,
        project=None,
        nocdn=False,
        htmlize=False,
        use_valign=False,
        rerender=False,
        pngtrick=False,
        bustcache=False):
    # look for $.$ or $$.$$
    if htmlize:
        nocdn = True
        branch = None
    temp_dir = tempfile.mkdtemp('', 'readme2tex-')

    with open(readme, encoding = 'utf-8') as readme_file:
        content = readme_file.read()
    content = content.replace('\r', '')

    equations = list(extract_equations(content))
    equation_map = {}
    seen = {}
    has_changes = False
    for equation, start, end, block in equations:
        if equation in seen:
            equation_map[(start, end)] = equation_map[seen[equation]]
            continue
        seen[equation] = (start, end)

        # Check if this already exists
        svg = None
        name = hashlib.md5(equation.encode('utf-8')).hexdigest()
        svg_path = os.path.join(svgdir, name + '.svg')
        if branch:
            try:
                svg = check_output(['git', 'show', '%s:%s' % (branch, svg_path.replace('\\', '/'))]).decode('utf-8')
            except Exception:
                logging.info("Cannot find %s:%s", branch, svg_path.replace('\\', '/'))
        else:
            if os.path.exists(svg_path):
                with open(svg_path, encoding = 'utf-8') as f:
                    svg = f.read()

        try:
            if svg and not rerender:
                xml = ET.fromstring(svg)
                offset = float(xml.attrib['{https://github.com/leegao/readme2tex/}offset'])
                equation_map[(start, end)] = (svg, name, None, offset)
                continue
        except Exception:
            logging.warning("Cached SVG file for %s is corrupt, rerendering.", svg_path)

        svg, dvi, name = rendertex(engine, equation, packages, temp_dir, block)
        svg = svg.decode('utf-8')

        xml = (ET.fromstring(svg))
        attributes = xml.attrib
        gfill = xml.find('{http://www.w3.org/2000/svg}g')
        gfill.set('fill-opacity', '0.9')
        if not block:
            uses = gfill.findall('{http://www.w3.org/2000/svg}use')
            use = uses[0]
            # compute baseline off of this dummy element
            x = use.attrib['x']
            y = float(use.attrib['y'])
            viewBox = [float(a) for a in attributes['viewBox'].split()] # min-x, min-y, width, height
            baseline_offset = viewBox[-1] - (y - viewBox[1])
            newViewBox = list(viewBox)

            newViewBox[0] = min(list(float(next.attrib['x']) for next in uses if next.attrib['x'] != x) or [float(x)])
            newViewBox[-2] -= abs(newViewBox[0] - viewBox[0])
            xml.set('viewBox', ' '.join(map(str, newViewBox)))
            xml.set('width', str(newViewBox[-2]) + 'pt')
            gfill.remove(use)
            top = y - newViewBox[1]
            bottom = baseline_offset
            if not use_valign:
                if top > bottom:
                    # extend the bottom
                    height = 2 * top
                    xml.set('height', '%spt' % (height))
                    newViewBox[-1] = height
                    xml.set('viewBox', ' '.join(map(str, newViewBox)))
                else:
                    # extend the top
                    height = 2 * bottom
                    xml.set('height', '%spt' % (height))
                    newViewBox[-1] = height
                    newViewBox[1] -= (height - bottom - top)
                    xml.set('viewBox', ' '.join(map(str, newViewBox)))
                    pass
        else:
            baseline_offset = 0

        xml.set('readme2tex:offset', str(baseline_offset))
        xml.set('xmlns:readme2tex', 'https://github.com/leegao/readme2tex/')
        svg = ET.tostring(xml).decode('utf-8')

        has_changes = True
        equation_map[(start, end)] = (svg, name, dvi, baseline_offset)

    # git rev-parse --abbrev-ref HEAD
    old_branch = "NONE"
    if branch:
        try:
            old_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode('utf-8').strip()
        except:
            if not nocdn:
                logging.error("Not in a git repository, please enable --nocdn")
            return exit(1)

    if has_changes:
        if not branch or branch == old_branch:
            branch = old_branch
            if not os.path.exists(svgdir):
                os.makedirs(svgdir)
            for equation, start, end, _ in equations:
                svg, name, dvi, off = equation_map[(start, end)]
                if dvi:
                    with open(os.path.join(svgdir, name + '.svg'), 'w', encoding = 'utf-8') as file:
                        file.write(svg)
                    if pngtrick:
                        svg2png(os.path.join(svgdir, name + '.svg'))
        else:
            # git stash -q --keep-index
            stashed = False
            if check_output(['git', 'status', '-s']).decode('utf-8').strip():
                if input(
                        "There are unstaged files, would you like to stash them? "
                        "(They will be automatically unstashed.) [(y)/n]").lower().startswith('n'):
                    logging.error("Aborting.")
                    return
                logging.info("Stashing...")
                check_output(['git', 'stash', '-u'])
                stashed = True
            try:
                logging.info("Checking out %s", branch)
                check_output(['git', 'checkout', branch])

                if not os.path.exists(svgdir):
                    os.makedirs(svgdir)
                for equation, start, end, _ in equations:
                    svg, name, dvi, off = equation_map[(start, end)]
                    if dvi:
                        with open(os.path.join(svgdir, name + '.svg'), 'w', encoding = 'utf-8') as file:
                            file.write(svg)
                        if pngtrick:
                            svg2png(os.path.join(svgdir, name + '.svg'))

                status = check_output(['git', 'status', '-s']).decode('utf-8').strip()
                if status:
                    logging.info(status)
                    logging.info("Committing changes...")
                    check_output(['git', 'add', svgdir])
                    check_output(['git', 'commit', '-m', 'readme2latex render'])
                else:
                    logging.info("No changes were made.")

                logging.info("Switching back to the original branch")
                check_output(['git', 'checkout', old_branch])
            except Exception as e:
                logging.error("%s", e)
                try:
                    logging.info("Cleaning up.")
                    check_output(['git', 'checkout', '--', '.'])
                    check_output(['git', 'clean', '-df'])
                    check_output(['git', 'checkout', old_branch])
                except Exception as e_:
                    logging.fatal("Could not cleanup. %s\n\nMake sure that you cleanup manually.", e_)
                if stashed:
                    logging.fatal("You have stashed changes on " + old_branch + ", make sure you unstash them there.")
                raise e

            if stashed:
                logging.info("Unstashing...")
                check_output(['git', 'stash', 'pop', '-q'])

    # Make replacements
    if not user or not project:
        try:
            # git remote get-url origin
            giturl = check_output(['git', 'remote', '-v']).strip().decode('utf-8').splitlines()[0]
            start = giturl.find('.com/') + 5
            userproj = giturl[start:]
            end = userproj.find('.git')
            user, project = userproj[:end].split('/')
        except:
            raise Exception("Please specify your github --username and --project.")

    if nocdn:
        svg_url = "{svgdir}/{name}.svg"
    else:
        svg_url = "https://cdn.jsdelivr.net/gh/{user}/{project}@{branch}/{svgdir}/{name}.svg"

    if pngtrick:
        svg_url = svg_url[:-4] + '.png'

    equations = sorted(equations, key=lambda x: (x[1], x[2]))[::-1]
    new = content
    for equation, start, end, block in equations:
        svg, name, dvi, off = equation_map[(start, end)]
        if abs(off) < 1e-2: off = 0
        xml = (ET.fromstring(svg))
        attributes = xml.attrib

        scale = 1.65
        height = float(attributes['height'][:-2]) * scale
        width = float(attributes['width'][:-2]) * scale
        url = svg_url.format(user=user, project=project, branch=branch, svgdir=svgdir, name=name)
        tail = []
        if bustcache:
            tail.append('%x' % random.randint(0, 1e12))
        img = '<img alt=%s src="%s%s" %s width="%spt" height="%spt"/>' % (
            quoteattr(equation),
            url,
            '?%s' % ('&'.join(tail)) if tail else '',
            ('valign=%spx'%(-off * scale) if use_valign else 'align="middle"'),
            width,
            height)
        if block: img = '<p align="center">%s</p>' % img
        new = new[:start] + img + new[end:]
    with open(output, 'w', encoding = 'utf-8') as outfile:
        outfile.write(new)

    if htmlize:
        try:
            import markdown
        except:
            logging.error("Cannot render markdown, make sure that the markdown package is installed.")
            return
        with open(output+".html", 'w', encoding = 'utf-8') as outfile:
            outfile.write(markdown.markdown(new))
