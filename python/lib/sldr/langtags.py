#!/usr/bin/python
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the University nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

from xml.etree import ElementTree as et
from xml.etree import ElementPath as ep
import os, re
from ldml import Ldml

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class LangTag(object) :

    lang = None
    script = None
    region = None
    variants = None
    extensions = None
    hidescript = False
    hideregion = False

    def __init__(self, tag=None, lang=None, script=None, region=None, variants=None, extensions=None) :
        self.lang = lang
        self.script = script
        self.region = region
        self.variants = variants
        self.extensions = extensions
        if tag is not None : self.parse(tag)

    def _extensions(self) :
        if self.extensions is None : return []
        res = []
        for ns in sorted(self.extensions.keys()) :
            res.append(ns)
            res.extend(sorted(self.extensions[ns]))
        return res

    def __str__(self) :
        """ Output the canonical tag with things hidden """
        subtags = [self.lang]
        if not self.hidescript : subtags.append(self.script)
        if not self.hideregion : subtags.append(self.region)
        if self.variants is not None : subtags.extend(self.variants)
        subtags.extend(self._extensions())
        return "-".join([x for x in subtags if x is not None])

    def __repr__(self) :
        """ Output the full tag with nothing hidden """
        subtags = [self.lang, self.script, self.region]
        if self.variants is not None : subtags.extend(self.variants)
        subtags.extend(self._extensions())
        return "-".join([x for x in subtags if x is not None])

    def __hash__(self) :
        return hash(str(self))

    def parse(self, x) :
        ''' cheap and nasty langtag parser '''
        params = {}
        bits = x.replace('_', '-').split('-')
        curr = 0
        if 1 < len(bits[curr]) < 4 :
            self.lang = bits[curr].lower()
            curr += 1
        if curr >= len(bits) : return
        if len(bits[curr]) == 4 :
            self.script = bits[curr].title()
            curr += 1
        if curr >= len(bits) : return
        if 1 < len(bits[curr]) < 4 :
            self.region = bits[curr].upper()
            curr += 1
        ns = ''
        extensions = {}
        variants = []
        while curr < len(bits) :
            if len(bits[curr]) == 1 :
                ns = bits[curr].lower()
                extensions[ns] = []
            elif ns == '' :
                variants.append(bits[curr].lower())
            else :
                extensions[ns].append(bits[curr].lower())
            curr += 1
        if len(variants) : self.variants = variants
        if len(extensions) : self.extensions = extensions

    def merge_equivalent(self, tag) :
        if self.script is None and self.script != tag.script :
            self.script = tag.script
        if self.script == tag.script and not self.hidescript :
            self.hidescript = tag.hidescript
        if self.region is None and self.region != tag.region :
            self.region = tag.region
        if self.region == tag.region and not self.hideregion :
            self.hideregion = tag.hideregion

    def allforms(self) :
        ss = [self.script]
        if self.hidescript :
            ss.append(None)
        rs = [self.region]
        if self.hideregion :
            rs.append(None)
        extras = []
        if self.variants is not None : extras.extend(self.variants)
        if self.extensions is not None :
            for ns in sorted(self.extensions.keys()) :
                extras.append(ns)
                extras.extend(sorted(self.extensions[ns]))
        res = ["-".join([x for x in [self.lang] + [s] + [r] + extras if x is not None]) for s in ss for r in rs]
        return res

    def matches(self, other) :
        if self.lang != other.lang : return False
        if self.script != other.script and not (self.hidescript and other.script is None) : return False
        if self.region != other.region and not (self.hideregion and other.region is None) : return False
        if self.variants != other.variants : return False
        if self.extensions != other.extensions : return False
        return True

    def analyse(self, alltags = None) :
        if alltags is None :
            lts = LangTags()
            alltags = lts.tags
        if str(self) in alltags :
            return alltags[str(self)]
        if self.region is not None :
            test = self.__class__(lang = self.lang, script = self.script, variants = self.variants, extensions = self.extensions)
            test = test.analyse(alltags)
            if str(test) in alltags :
                self.merge_equivalent(test)
            elif self.variants is not None or self.extensions is not None :
                test = self.__class__(lang = self.lang, region = self.region)
                test = test.analyse(alltags)
                self.merge_equivalent(test)
        elif self.script is not None :
            test = self.__class__(lang = self.lang, variants = self.variants, extensions = self.extensions)
            test = test.analyse(alltags)
            if str(test) in alltags :
                self.merge_equivalent(test)
            elif self.variants is not None or self.extensions is not None :
                test = self.__class__(lang = self.lang, script = self.script)
                test = test.analyse(alltags)
                self.merge_equivalent(test)

        # now the oddeties
        if self.variants is not None :
            if not self.hidescript and self.script == 'Latn' : 
                for v in ('fonipa', 'fonapa', 'fonupa') :
                    if v in self.variants :
                        self.hidescript = True
                        break
        return self


class LangTags(object) :

    __metaclass__ = Singleton

    def __init__(self, paths = None) :
        """ Everything is keyed by language """
        self.tags = {}

        self.readIana()
        self.readLikelySubtags()
        self.readSupplementalData()

    def readLikelySubtags(self, fname = None) :
        """Reads the likely subtag mappings"""
        if fname is None :
            fname = os.path.join(os.path.dirname(__file__), 'likelySubtags.xml')
        doc = et.parse(fname)
        ps = doc.getroot().find('likelySubtags')
        for p in ps.findall('likelySubtag') :
            to = LangTag(p.get('to'))
            base = LangTag(p.get('from'))
            to = to.analyse(self.tags)
            if base.script is None : to.hidescript = True
            if base.region is None : to.hideregion = True
            for t in to.allforms() :
                self.tags[t] = to

    def readIana(self, fname = None) :
        """Reads the iana registry, particularly ths suppress script info"""
        if fname is None :
            fname = os.path.join(os.path.dirname(__file__), "language-subtag-registry.txt")
        with open(fname) as f :
            currlang = None
            mode = None
            for l in f.readlines() :
                l = l.strip()
                if l.startswith("Type: ") :
                    mode = l[6:]
                elif l.startswith("Subtag: ") :
                    if mode == "language" :
                        currlang = l[8:]
                elif l.startswith("Suppress-Script: ") and currlang is not None :
                    tag = LangTag(lang=currlang, script=l[17:])
                    tag.hidescript = True
                    for t in tag.allforms() :
                        if str(t) not in self.tags : self.tags[str(t)] = tag

    def readSupplementalData(self, fname = None) :
        """Reads supplementalData.xml from CLDR to get useful structural information on LDML"""
        scripts = {}
        territories = {}
        regions = {}
        if fname is None :
            fname = os.path.join(os.path.dirname(__file__), 'supplementalData.xml')
        doc = et.parse(fname)
        ps = doc.getroot().find('languageData')
        for p in ps.findall('language') :
            lang = p.get('type')
            ss = scripts.get(lang, [])
            ts = territories.get(lang, [])
            if p.get('scripts') :
                ss += p.get('scripts').split(' ')
                scripts[lang] = ss
            if p.get('territories') :
                ts += p.get('territories').split(' ')
                territories[lang] = ts
        ps = doc.getroot().find('territoryInfo')
        for p in ps.findall('territory') :
            r = p.get('type')
            for l in p.findall('languagePopulation') :
                lt = l.get('type')
                if lt not in regions : regions[lt] = []
                regions[lt].append(r)
        # set default scripts and regions based on there being only one for a language
        for l, r in regions.items() :
            if len(r) > 1 : continue
            r = r[0]
            t = LangTag(l)      # could include script
            if str(t) in self.tags :
                t = self.tags[str(t)]
            if t.region is None :
                t.region = r
                t.hideregion = True
            elif t.region != r :
                t = LangTag(l, region=r)
            if t.script is None and l in scripts and len(scripts[l]) == 1 :
                t.script = scripts[l][0]
                t.hidescript = True
            t = t.analyse(self.tags)
            for a in t.allforms() :
                if a not in self.tags : self.tags[a] = t

if __name__ == '__main__' :
    import sys

    def find_file(tagstr, root='.') :
        fname = tagstr.replace('-', '_') + '.xml'
        testf = os.path.join(root, fname)
        if os.path.exists(testf) : return testf
        testf = os.path.join(root, fname[0], fname)
        if os.path.exists(testf) : return testf
        return None

    res = []
    indir = ['sldr']
    lts = LangTags(paths=indir)
    for k in sorted(lts.tags.keys()) :
        t = lts.tags[k]
        if str(t) == k :
            outs = sorted(t.allforms(), key = len)
            res.append(outs)
    alllocales = set()
    if len(sys.argv) < 2 :
        for d in indir :
            for l in os.listdir(d) :
                if l.endswith('.xml') :
                    if 1 < len(l.split('_', 1)[0]) < 4 :
                        alllocales.add(l[:-4])
                elif os.path.isdir(os.path.join(d, l)) :
                    for s in os.listdir(os.path.join(d, l)) :
                        if s.endswith('.xml') :
                            if 1 < len(s.split('_', 1)[0]) < 4 :
                                alllocales.add(s[:-4])
    for l in alllocales :
        t = LangTag(l)
        if str(t) not in lts.tags :
            t = t.analyse(lts.tags)
            lts.tags[str(t)] = t
            outs = sorted(t.allforms(), key = len)
            res.append(outs)
    outstrings = []
    for o in res :
        outstrings.append(" = ".join(["*" + x if find_file(x, indir[0]) else x for x in o]))
    print "\n".join(sorted(outstrings, key=lambda x:x.replace('*', '')))

