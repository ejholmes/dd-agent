# stdlib
import subprocess

# project
from checks import AgentCheck


def query_txt(name):
    """Queries the TXT record for a domain name using dig."""
    return subprocess.Popen(['dig', '+short', 'chaos', 'txt', name], stdout=subprocess.PIPE).communicate()[0].strip()


class Dnsmasq(AgentCheck):
    """Scrapes statistics from the .bind domain in dnsmasq. Requires dnsmasq v2.69+"""

    def check(self, instance):
        self.gauge('dnsmasq.cachesize', self.value('cachesize.bind'))
        self.gauge('dnsmasq.insertions', self.value('insertions.bind'))
        self.gauge('dnsmasq.evictions', self.value('evictions.bind'))
        self.gauge('dnsmasq.misses', self.value('misses.bind'))
        self.gauge('dnsmasq.hits', self.value('hits.bind'))

    def value(self, name):
        """Queries a TXT record, then cleans the double quotes and converts it to an int"""
        return int(self.query_txt(name).replace('"', ''))

    def query_txt(self, name):
        return query_txt(name)
