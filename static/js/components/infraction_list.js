// Also must change python definition
const INFRACTIONS_PER_PAGE = 30;

// Show the bottom page navigation when a page has more than this many infractions
const BOTTOM_NAV_THRESHOLD = 15;

function setupNav(current_page, total_pages, page_rows) {
    // Reset the blocks

    const top_nav = document.getElementById('infraction-pages');
    const top_compact = document.getElementById('infraction-pages-compact');
    const bottom_nav = document.getElementById('infraction-pages-bottom');
    const bottom_compact = document.getElementById('infraction-pages-bottom-compact');

    $(top_nav).empty();
    $(top_compact).empty();
    $(bottom_nav).empty();
    $(bottom_compact).empty();
    $('#infraction-pages-bottom-nav').addClass('is-hidden');

    // We do not render the navbar when there are only one page of bans to show
    if (total_pages <= 1) {
        return;
    }

    renderNav(top_nav, current_page, total_pages);
    renderCompactNav(top_compact, current_page, total_pages);

    if (page_rows > BOTTOM_NAV_THRESHOLD) {
        renderNav(bottom_nav, current_page, total_pages);
        renderCompactNav(bottom_compact, current_page, total_pages);
        $('#infraction-pages-bottom-nav').removeClass('is-hidden');
    }
}

function renderNav(nav, current_page, total_pages) {
    // Embedded function to make us a button
    function make_button(page_n) {
        const page_li = document.createElement('li');
        const page_a = document.createElement('a');

        page_a.classList.add('pagination-link', 'text-primary');
        page_a.innerText = (page_n).toString();

        if (page_n === current_page) {
            page_a.classList.remove('text-primary');
            page_a.classList.add('is-current', 'is-accent', 'has-white-text');
        } else {
            $(page_a).click(function () {
                insertParam('page', page_n);
            });
        }

        page_li.appendChild(page_a);

        nav.appendChild(page_li);
    }

    function make_dots() {
        const page_li = document.createElement('li');
        const page_span = document.createElement('span');

        page_span.classList.add('pagination-ellipsis', 'text-primary');
        page_span.innerText = '…';

        page_li.appendChild(page_span);

        nav.appendChild(page_li);
    }

    for (let i = 0; i < total_pages; i++) {
        if (i === 0) {
            make_button(1);

            if (current_page >= 5) {
                make_dots();
            }
        } else if (
            i === (current_page - 1)
            || i === (current_page - 1) - 1
            || i === (current_page - 1) - 2
            || i === (current_page - 1) + 1
            || i === (current_page - 1) + 2
        ) {
            make_button(i + 1);

            if (i === (current_page - 1) + 2 && total_pages - current_page > 2) {
                if (total_pages - current_page !== 3) {
                    make_dots();
                }
                make_button(total_pages);
            }
        }
    }
}


// Compact pagination: < "Page X of Y" >
function renderCompactNav(compact, current_page, total_pages) {
    function make_step(page_n, icon, label) {
        const step_a = document.createElement('a');
        step_a.classList.add('text-link');
        step_a.setAttribute('aria-label', label);

        const step_icon = document.createElement('i');
        step_icon.classList.add('fas', icon);
        step_a.appendChild(step_icon);

        if (page_n < 1 || page_n > total_pages) {
            step_a.setAttribute('disabled', '');
        } else {
            $(step_a).click(function () {
                insertParam('page', page_n);
            });
        }

        compact.appendChild(step_a);
    }

    make_step(current_page - 1, 'fa-chevron-left', 'Previous page');

    const page_label = document.createElement('span');
    page_label.classList.add('text-primary');
    page_label.innerText = 'Page ' + current_page + ' of ' + total_pages;
    compact.appendChild(page_label);

    make_step(current_page + 1, 'fa-chevron-right', 'Next page');
}

const services = {
    'steam': ['fab', 'fa-steam']
};

const restrictions = {
    'voice': ['fas', 'fa-volume-mute', 'is-voice'],
    'ban': ['fas', 'fa-ban', 'is-ban'],
    'text': ['fas', 'fa-comment-slash', 'is-text'],
    'call-admin': ['fas', 'fa-phone-slash', 'is-call-admin'],
    'admin-chat': ['fas', 'fa-bell-slash', 'is-admin-chat'],
    'item': ['fas', 'fa-virus-slash', 'is-item'],
    'warning': ['fas', 'fa-exclamation-triangle', 'is-warning'],
};

const flags_to_str = new Map();

flags_to_str.set(INFRACTION.VOICE_BLOCK, 'voice');
flags_to_str.set(INFRACTION.CHAT_BLOCK, 'text');
flags_to_str.set(INFRACTION.BAN, 'ban');
flags_to_str.set(INFRACTION.CALL_ADMIN_BAN, 'call-admin');
flags_to_str.set(INFRACTION.ADMIN_CHAT_BLOCK, 'admin-chat');
flags_to_str.set(INFRACTION.ITEM_BLOCK, 'item');

function addInfractionRow(infraction) {
    const unixNow = Date.now() / 1000;

    const row = document.createElement('tr');
    row.classList.add('infraction-row');

    // Utility function to create the wrapper for the text
    function getWrapper(el) {
        const w = document.createElement('div');
        w.classList.add('has-text-centered', 'text-primary');
        el.appendChild(w);

        return w;
    }

    // The service logo
    let fa_type = 'fas';
    let fa_icon = 'fa-globe';

    if (
        infraction['player'].hasOwnProperty('gs_service')
        && services.hasOwnProperty(infraction['player']['gs_service'])
    ) {
        fa_type = services[infraction['player']['gs_service']][0];
        fa_icon = services[infraction['player']['gs_service']][1];
    }

    const svc_cell = document.createElement('td');
    svc_cell.classList.add('vertical-center', 'is-hidden-touch');

    const svc_wrap = getWrapper(svc_cell);
    const svc_icon = document.createElement('i');
    svc_icon.classList.add(fa_type, fa_icon, 'fa24');

    svc_wrap.appendChild(svc_icon);
    row.appendChild(svc_cell);

    // The time
    const date = new Date(infraction['created'] * 1000);
    const dateStr = date.getFullYear() + '/' + (date.getMonth() + 1) + '/' + date.getDate() + ' '
        + (date.getHours() >= 10 ? date.getHours() : '0' + date.getHours()) + ':'
        + (date.getMinutes() >= 10 ? date.getMinutes() : '0' + date.getMinutes());

    const date_cell = document.createElement('td');
    date_cell.classList.add('vertical-center', 'is-hidden-touch');

    const date_wrap = getWrapper(date_cell);
    const date_span = document.createElement('span');
    date_span.innerText = dateStr;
    date_wrap.appendChild(date_span);
    row.appendChild(date_cell);

    // Small "service icon + date" line
    function makeMeta(text) {
        const meta = document.createElement('div');
        meta.classList.add('infraction-meta');
        meta.setAttribute('title', dateStr);

        const meta_icon = document.createElement('i');
        meta_icon.classList.add(fa_type, fa_icon);
        meta.appendChild(meta_icon);

        const meta_text = document.createElement('span');
        meta_text.innerText = text;
        meta.appendChild(meta_text);

        return meta;
    }

    // Infraction icons
    function appendRestrictionIcons(el) {
        let b = false;

        flags_to_str.forEach(function (v, k) {
            if (infraction['flags'] & k) {
                b = true;

                const a = restrictions[v];

                const ri = document.createElement('i');
                ri.classList.add(a[0], a[1], a[2]);
                el.appendChild(ri);
            }
        });

        if (!b) {
            const a = restrictions['warning'];

            const ri = document.createElement('i');
            ri.classList.add(a[0], a[1], a[2]);
            el.appendChild(ri);
        }
    }

    const restrictions_cell = document.createElement('td');
    restrictions_cell.classList.add('vertical-center', 'is-hidden-touch');

    appendRestrictionIcons(getWrapper(restrictions_cell));

    row.appendChild(restrictions_cell);

    // User
    let uicon = '/static/images/fallback_av.png';

    if (infraction['player'].hasOwnProperty('gs_avatar')) {
        uicon = '/file/uploads/' + infraction['player']['gs_avatar']['file_id'] + '/avatar.webp';
    }

    let uname = 'Unknown Player';

    if (infraction['player'].hasOwnProperty('gs_name')) {
        uname = infraction['player']['gs_name'];
    } else if (infraction['player'].hasOwnProperty('ip') && infraction['player']['ip'] !== 'MISSING_PERMISSIONS') {
        uname = infraction['player']['ip'];
    } else if (!infraction['player'].hasOwnProperty('gs_id')) { // Assume IP ban
        uname = 'IP Address';
    }

    const user_cell = document.createElement('td');
    user_cell.classList.add('vertical-center', 'has-text-centered-desktop', 'text-primary', 'inf-col-user');

    const user_wrap = document.createElement('div');
    user_wrap.classList.add('infraction-user');
    user_cell.appendChild(user_wrap);

    const uimg = document.createElement('img');
    uimg.classList.add('infraction-user-av');
    uimg.setAttribute('src', uicon);
    user_wrap.appendChild(uimg);

    const user_text = document.createElement('div');
    user_text.classList.add('infraction-user-text');
    user_wrap.appendChild(user_text);

    const utxt = document.createElement('span');
    utxt.classList.add('infraction-user-name');
    utxt.innerText = uname;
    user_text.appendChild(utxt);

    // "by <admin>" + restriction icons, mobile, tablet
    const user_sub = document.createElement('div');
    user_sub.classList.add('infraction-user-sub', 'is-hidden-desktop');
    user_text.appendChild(user_sub);

    const user_sub_icons = document.createElement('span');
    user_sub_icons.classList.add('infraction-icons', 'is-phone-only');
    appendRestrictionIcons(user_sub_icons);
    user_sub.appendChild(user_sub_icons);

    const user_sub_admin = document.createElement('span');
    user_sub.appendChild(user_sub_admin);

    row.appendChild(user_cell);

    // Restrictions and creation date, as its own column on tablet only
    const summary_cell = document.createElement('td');
    summary_cell.classList.add('vertical-center', 'is-hidden-phone', 'is-hidden-desktop', 'inf-col-summary');

    const summary_icons = document.createElement('div');
    summary_icons.classList.add('infraction-icons');
    appendRestrictionIcons(summary_icons);
    summary_cell.appendChild(summary_icons);

    summary_cell.appendChild(makeMeta(moment(date).format('MMM D, HH:mm')));

    row.appendChild(summary_cell);

    // Admin
    const admin_cell = document.createElement('td');
    admin_cell.classList.add('vertical-center', 'has-text-centered', 'is-hidden-touch', 'text-primary');

    const aimg = document.createElement('img');
    aimg.classList.add('infraction-user-av', 'mr-2');
    aimg.setAttribute('src', '/static/images/fallback_av.png');
    admin_cell.appendChild(aimg);

    const atxt = document.createElement('span');
    admin_cell.appendChild(atxt);

    function setAdminName(name) {
        atxt.innerText = name;
        user_sub_admin.innerText = 'by ' + name;
    }

    setAdminName('Fetching...');

    if (infraction['flags'] & (INFRACTION.SYSTEM) || !infraction.hasOwnProperty('admin')) { // System infraction
        setAdminName('System');
    } else {
        get_admin(infraction['admin']).then(result => {
            if (result.hasOwnProperty('avatar_id')) {
                aimg.setAttribute('src', '/file/uploads/' + result['avatar_id'] + '/avatar.webp');
            }

            if (result.hasOwnProperty('admin_name')) {
                setAdminName(result['admin_name']);
            } else {
                setAdminName('Unknown Admin');
            }
        });
    }

    // Time remaining

    const time_cell = document.createElement('td');
    time_cell.classList.add(
        'vertical-center', 'has-text-centered-desktop', 'has-text-right-touch', 'inf-col-remaining'
    );

    const time_text = document.createElement('span');
    time_text.classList.add('infraction-remaining');
    const time_icon = document.createElement('i');
    time_icon.classList.add('mr-1');
    time_text.appendChild(time_icon);

    // Mobile/Tablet needs compacted text
    const time_texts = getTimeRemainingTexts(infraction);
    const time_layouts = [
        ['desktop', 'is-hidden-touch'],
        ['tablet', 'is-hidden-phone', 'is-hidden-desktop'],
        ['phone', 'is-phone-only']
    ];

    for (const [layout, ...hidden_classes] of time_layouts) {
        const is = document.createElement('span');
        is.classList.add(...hidden_classes);
        is.innerText = time_texts[layout];
        time_text.appendChild(is);
    }

    time_cell.appendChild(time_text);

    const date_short = moment(date).isSame(moment(), 'day') ? 'HH:mm' : 'MMM D';
    const time_meta = makeMeta(moment(date).format(date_short));
    time_meta.classList.add('is-phone-only');
    time_cell.appendChild(time_meta);

    // Color and icons
    if (infraction['flags'] & INFRACTION.REMOVED) {
        time_text.classList.add('has-text-warning');
        time_icon.classList.add('fas', 'fa-ankh');
    } else if (infraction['flags'] & INFRACTION.PERMANENT) {
        time_text.classList.add('has-text-danger');
        time_icon.classList.add('fas', 'fa-skull');
    } else if (
        infraction['flags'] & INFRACTION.SESSION
        || (infraction.hasOwnProperty('time_left') && infraction['time_left'] <= 0)
        || (infraction.hasOwnProperty('expires') && infraction['expires'] < unixNow)
    ) {
        time_text.classList.add('has-text-success');
        time_icon.classList.add('fas', 'fa-check');
    } else if (
        infraction['flags'] & INFRACTION.PLAYTIME_DURATION
        && (
            (infraction.hasOwnProperty('last_heartbeat') && (infraction['last_heartbeat'] + 300) < unixNow)
            || !infraction.hasOwnProperty('last_heartbeat')
        )
    ) {
        time_text.classList.add('text-secondary');
        time_icon.classList.add('fas', 'fa-pause');
    } else {
        time_text.classList.add('has-text-orange');
        time_icon.classList.add('fas', 'fa-stopwatch');
    }

    row.appendChild(admin_cell);
    row.appendChild(time_cell);

    row.setAttribute('data-infraction', infraction['id']);

    $(row).click(function () {
        openInfraction(row.getAttribute('data-infraction'));
    });

    const ibase = document.getElementById('infractionBase');
    ibase.appendChild(row);
}

const SHORT_DURATION_UNITS = {
    'second': 's',
    'minute': 'm',
    'hour': 'h',
    'day': 'd',
    'week': 'w',
    'month': 'mo',
    'year': 'y'
};

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

// "a few seconds" -> "few seconds", "an hour" -> "1 hour", "26 minutes" stays as is
function humanizeDuration(ms) {
    return moment.duration(ms).humanize().replace(/^a few /, 'few ').replace(/^an? /, '1 ');
}

// "few seconds" -> "Seconds", "1 hour" -> "1h", "26 minutes" -> "26m"
function shortenDuration(ms) {
    const [amount, unit] = humanizeDuration(ms).split(' ');

    if (amount === 'few') {
        return 'few secs';
    }

    return amount + SHORT_DURATION_UNITS[unit.replace(/s$/, '')];
}

function getTimeRemainingTexts(infraction) {
    // Simple cases that do not require any other work
    if (infraction['flags'] & INFRACTION.REMOVED) {
        // Session and permanent infractions never had a length to show
        const has_length = !(infraction['flags'] & (INFRACTION.SESSION | INFRACTION.PERMANENT));
        let original = 0;

        if (has_length && infraction['flags'] & INFRACTION.PLAYTIME_DURATION) {
            if (infraction.hasOwnProperty('orig_length')) {
                original = infraction['orig_length'] * 1000;
            }
        } else if (has_length) {
            original = (infraction['expires'] - infraction['created']) * 1000;
        }

        if (original <= 0) {
            return {desktop: 'Removed', tablet: 'Removed', phone: 'Removed'};
        }

        return {
            desktop: 'Removed (' + capitalize(moment.duration(original).humanize()) + ')',
            tablet: 'Removed · ' + humanizeDuration(original),
            phone: 'Removed'
        };
    } else if (infraction['flags'] & INFRACTION.SESSION) {
        return {desktop: 'Session', tablet: 'Session', phone: 'Session'};
    } else if (infraction['flags'] & INFRACTION.PERMANENT) {
        return {desktop: 'Permanent', tablet: 'Permanent', phone: 'Permanent'};
    }

    // For both standard infractions and pausable infractions, we'd like to show remaining and original
    let remaining = 0;
    let original = 0;

    if (infraction['flags'] & INFRACTION.PLAYTIME_DURATION) {
        remaining = infraction['time_left'] * 1000;

        // Infraction might not have this attribute
        if (infraction.hasOwnProperty('orig_length')) {
            original = infraction['orig_length'] * 1000;
        }
    } else {
        const unixNow = Date.now() / 1000;
        remaining = (infraction['expires'] - unixNow) * 1000;
        original = (infraction['expires'] - infraction['created']) * 1000;
    }

    if (remaining > 0) {
        const short = shortenDuration(remaining);

        return {
            desktop: capitalize(moment.duration(remaining).humanize()),
            tablet: capitalize(humanizeDuration(remaining)) + ' left',
            phone: short === 'Seconds' ? short : short + ' left'
        };
    } else {
        return {
            desktop: 'Expired (' + capitalize(moment.duration(original).humanize()) + ')',
            tablet: 'Expired · ' + humanizeDuration(original),
            phone: 'Expired'
        };
    }
}
