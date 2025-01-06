// Also must change python definition
const INFRACTIONS_PER_PAGE = 30;

function setupNav(current_page, total_pages) {
    // Reset the block

    const nav = document.getElementById('infraction-pages');

    $(nav).empty();

    // We do not render the navbar when there are only one page of bans to show
    if (total_pages === 1) {
        return;
    }

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


const services = {
    'steam': ['fab', 'fa-steam']
};

const restrictions = {
    'voice': ['fas', 'fa-volume-mute', 'is-voice'],
    'ban': ['fas', 'fa-ban', 'is-ban'],
    'text': ['fas', 'fa-comment-slash', 'is-text'],
    'call-admin': ['fas', 'fa-phone-slash', 'is-call-admin'],
    'admin-chat': ['fas', 'fa-hands-helping', 'is-admin-chat'],
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
    svc_cell.classList.add('vertical-center', 'is-hidden-mobile');

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

    // Infraction icons
    const restrictions_cell = document.createElement('td');
    restrictions_cell.classList.add('vertical-center', 'is-hidden-mobile-tiny');

    const restrictions_wrap = getWrapper(restrictions_cell);

    let b = false;

    flags_to_str.forEach(function (v, k) {
        if (infraction['flags'] & k) {
            b = true;

            const a = restrictions[v];

            const ri = document.createElement('i');
            ri.classList.add(a[0], a[1], a[2]);
            restrictions_wrap.appendChild(ri);
        }
    });

    if (!b) {
        const a = restrictions['warning'];

        const ri = document.createElement('i');
        ri.classList.add(a[0], a[1], a[2]);
        restrictions_wrap.appendChild(ri);
    }

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
    user_cell.classList.add('vertical-center', 'has-text-centered', 'text-primary');

    const uimg = document.createElement('img');
    uimg.classList.add('infraction-user-av', 'mr-2');
    uimg.setAttribute('src', uicon);
    user_cell.appendChild(uimg);

    const utxt = document.createElement('span');
    utxt.innerText = uname;
    user_cell.appendChild(utxt);

    row.appendChild(user_cell);

    // Admin
    const admin_cell = document.createElement('td');
    admin_cell.classList.add('vertical-center', 'has-text-centered', 'is-hidden-mobile', 'text-primary');

    const aimg = document.createElement('img');
    aimg.classList.add('infraction-user-av', 'mr-2');
    aimg.setAttribute('src', '/static/images/fallback_av.png');
    admin_cell.appendChild(aimg);

    const atxt = document.createElement('span');
    atxt.innerText = 'Fetching...';
    admin_cell.appendChild(atxt);

    if (infraction['flags'] & (INFRACTION.SYSTEM) || !infraction.hasOwnProperty('admin')) { // System infraction
        atxt.innerText = 'System';
    } else {
        get_admin(infraction['admin']).then(result => {
            if (result.hasOwnProperty('avatar_id')) {
                aimg.setAttribute('src', '/file/uploads/' + result['avatar_id'] + '/avatar.webp');
            }

            if (result.hasOwnProperty('admin_name')) {
                atxt.innerText = result['admin_name'];
            } else {
                atxt.innerText = 'Unknown Admin';
            }
        });
    }

    // Time remaining

    const time_cell = document.createElement('td');
    time_cell.classList.add('vertical-center');

    const time_wrapper = document.createElement('div');
    time_wrapper.classList.add('has-text-centered');

    time_cell.appendChild(time_wrapper);

    const time_text = document.createElement('span');
    const time_icon = document.createElement('i');
    time_icon.classList.add('mr-1');
    time_text.appendChild(time_icon);
    const it = getTimeRemainingText(infraction);

    const is = document.createElement('span');
    is.innerText = it;
    time_text.appendChild(is);

    time_wrapper.appendChild(time_text);

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
        infraction['flags'] & INFRACTION.DEC_ONLINE_ONLY
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

function getTimeRemainingText(infraction) {
    let original = 0;

    // Simple cases that do not require any other work
    if (infraction['flags'] & INFRACTION.REMOVED) {
        if (infraction['flags'] & INFRACTION.SESSION || infraction['flags'] & INFRACTION.PERMANENT) {
            return 'Removed';
        }

        if (infraction['flags'] & INFRACTION.DEC_ONLINE_ONLY) {
            if (infraction.hasOwnProperty('orig_length')) {
                original = infraction['orig_length'] * 1000;
            }
        } else {
            original = (infraction['expires'] - infraction['created']) * 1000;
        }

        if (original <= 0) {
            return 'Removed';
        }

        const o_dur = moment.duration(original).humanize();

        return 'Removed (' + o_dur.charAt(0).toUpperCase() + o_dur.slice(1) + ')';
    } else if (infraction['flags'] & INFRACTION.SESSION) {
        return 'Session';
    } else if (infraction['flags'] & INFRACTION.PERMANENT) {
        return 'Permanent';
    }

    // For both standard infractions and pausable infractions, we'd like to show remaining and original
    let remaining = 0;
    original = 0;

    if (infraction['flags'] & INFRACTION.DEC_ONLINE_ONLY) {
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

    const r_dur = moment.duration(remaining).humanize();
    const o_dur = moment.duration(original).humanize();

    if (remaining > 0) {
        return r_dur.charAt(0).toUpperCase() + r_dur.slice(1);
    } else {
        return 'Expired (' + o_dur.charAt(0).toUpperCase() + o_dur.slice(1) + ')';
    }
}
