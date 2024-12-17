const urlParams = new URLSearchParams(window.location.search);

function handleResp(d, page, s, m) {
    if (!d.ok) {
        d.json().then(data => {
            if (data.detail)
                logException(data.detail);
        });
        throw new Error(defaultAPIError);
    }

    d.json().then(data => {
        const dur = 200 - (new Date().getTime() - s);

        function _loadI() {
            for (let i = 0; i < data['results'].length; i++) {
                addInfractionRow(data['results'][i]);
            }

            $('#resultCount').text(data['total_matched']);

            const total_pages = Math.ceil(data['total_matched'] / 30);

            if (total_pages < page && total_pages > 0) {
                //Out of range
                insertParam('page', total_pages);
            }

            setupNav(page, total_pages);

            if (m !== '') {
                resetViewModal();
                _openInfraction(m, s);
            } else {
                unsetLoading();
            }

            if (data['total_matched'] === 0 || data['results'] === 0) {
                setupEmptyINotice();
            }

            $('#infractions_tab').removeClass('is-hidden');
        }

        if (dur > 0) {
            setTimeout(_loadI, dur);
        } else {
            _loadI();
        }
    });
}

function setupEmptyINotice() {

    const i_root = document.getElementById('infractions_tab');

    $(i_root).empty();

    i_root.classList.add('has-text-centered');
    i_root.classList.remove('table-container');

    const icon = document.createElement('i');
    icon.classList.add('fas', 'fa-question', 'mt-5', 'nf-icon', 'text-primary');

    const text = document.createElement('h1');
    text.innerText = 'No Infractions';
    text.classList.add('is-size-1');

    const subtext = document.createElement('p');
    /* eslint-disable-next-line max-len */
    subtext.innerText = 'Your query matched no documents. Try a different search or add an infraction using the hammer icon in the top-left corner.';
    subtext.classList.add('mb-5');

    i_root.appendChild(icon);
    i_root.appendChild(text);
    i_root.appendChild(subtext);
}

function loadInfractions(page = 1, s, m) {
    gbRequest('GET', '/api/infractions?limit=30&skip=' + ((page - 1) * 30), null).then(function (a) {
        handleResp(a, page, s, m);
    }).catch(e => {
        logException(e);
    });
}

function doSearch(page = 1, s, m) {
    let query = '/api/infractions/search?limit=30&skip=' + ((page - 1) * 30);

    for (let i = 0; i < searchParams.length; i++) {
        if (urlParams.has(searchParams[i]) && urlParams.get(searchParams[i]).length > 0)
            query = query.concat(`&${searchParams[i]}=${encodeURIComponent(urlParams.get(searchParams[i]))}`);
    }
    gbRequest('GET', query, null).then(function (a) {
        handleResp(a, page, s, m);
    }).catch(e => {
        logException(e);
    });
}

function isSearch() {
    for (let i = 0; i < searchParams.length; i++) {
        if (urlParams.has(searchParams[i]) && urlParams.get(searchParams[i]).length > 0)
            return true;
    }
    return false;
}

$(document).ready(function () {
    const start = new Date().getTime();

    setLoading();

    let page = 1;

    const po = getMeta('page_override');
    const pq = urlParams.get('page');

    if (po !== '') {
        page = parseInt(po);
    } else if (pq != null) {
        page = parseInt(pq);
    }

    if (page < 1) {
        insertParam('page', 1);
    }

    const m = getMeta('load_infraction');

    if (isSearch) {
        doSearch(page, start, m);
    } else {
        loadInfractions(page, start, m);
    }
});
