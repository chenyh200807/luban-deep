// pages/text/text.js
Page({
  data: {
    url:''
  },

  isAllowedHost(hostname = '') {
    const host = String(hostname || '').trim().toLowerCase();
    if (!host) return false;
    return (
      host === 'www.yousenjiaoyu.com' ||
      host === 'test2.yousenjiaoyu.com' ||
      host === 'user.yousenjiaoyu.com' ||
      host.endsWith('.yousenjiaoyu.com') ||
      host === 'work.weixin.qq.com' ||
      host === 'channels.weixin.qq.com'
    );
  },

  sanitizeAbsoluteUrl(rawUrl) {
    const source = String(rawUrl || '').trim();
    if (!source) return '';
    const match = source.match(/^(https?):\/\/([^\/?#]+)([^\s]*)$/i);
    if (!match) {
      return '';
    }
    const protocol = match[1].toLowerCase();
    const hostname = match[2].toLowerCase();
    const suffix = match[3] || '';
    if (!['http', 'https'].includes(protocol)) {
      return '';
    }
    if (!this.isAllowedHost(hostname)) {
      return '';
    }
    return `${protocol}://${hostname}${suffix}`;
  },

  normalizeTargetUrl(options = {}) {
    if (options.url) {
      let decodedUrl = '';
      try {
        decodedUrl = decodeURIComponent(options.url);
      } catch (_) {
        decodedUrl = options.url;
      }
      const sanitizedUrl = this.sanitizeAbsoluteUrl(decodedUrl);
      if (sanitizedUrl) {
        return sanitizedUrl;
      }
    }

    if (options.urlname) {
      const sanitizedUrlName = this.sanitizeAbsoluteUrl(options.urlname);
      if (sanitizedUrlName) {
        return sanitizedUrlName;
      }

      const baseUrl = options.online === 'true'
        ? 'https://www.yousenjiaoyu.com'
        : 'https://test2.yousenjiaoyu.com';

      return `${baseUrl}/getwx/urlname/${options.urlname}`;
    }

    if (options.cid) {
      return `https://www.yousenjiaoyu.com/checkxcx?cid=${options.cid}`;
    }

    return 'https://www.yousenjiaoyu.com';
  },

  onLoad(options) {
      this.setData({
        url: this.normalizeTargetUrl(options)
      });
  }
})
